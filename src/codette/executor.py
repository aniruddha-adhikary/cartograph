"""Rule executor: run one rule against one parsed file."""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Any

from tree_sitter import Node as TSNode
from tree_sitter import QueryCursor

from .graph import Edge, Graph, Node
from .ids import stable_node_id
from .pack import Rule
from .templates import render
from .version import __version__


@dataclass
class ExecutionMetrics:
    files_matched: int = 0
    nodes_emitted: int = 0
    edges_emitted: int = 0
    errors: int = 0
    wall_ms: float = 0.0


class RuleError(Exception):
    def __init__(self, rule_id: str, file: str, message: str) -> None:
        super().__init__(f"{rule_id} @ {file}: {message}")
        self.rule_id = rule_id
        self.file = file
        self.message = message


def _node_text(node: TSNode) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text is not None else ""


def _capture_dict(node: TSNode) -> dict[str, Any]:
    return {
        "text": _node_text(node),
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "start_byte": node.start_byte,
        "end_byte": node.end_byte,
    }


def _where_passes(where: dict[str, dict[str, Any]], ctx: dict[str, Any]) -> bool:
    for name, conds in where.items():
        if name not in ctx:
            return False
        text = ctx[name]["text"] if isinstance(ctx[name], dict) else str(ctx[name])
        for op, arg in conds.items():
            if op == "in":
                if text not in arg:
                    return False
            elif op == "not_in":
                if text in arg:
                    return False
            elif op == "regex":
                if not re.search(arg, text):
                    return False
            elif op == "eq":
                if text != arg:
                    return False
            else:
                raise RuleError("where", "", f"unknown where operator {op!r}")
    return True


def _file_matches_when(rule: Rule, language_name: str, file_relpath: str, source: bytes) -> bool:
    if rule.language != language_name and not (
        rule.language == "javascript" and language_name in ("javascript",)
        or rule.language == "typescript" and language_name == "typescript"
        or rule.language == "tsx" and language_name == "tsx"
    ):
        return False
    if rule.file_glob and not fnmatch.fnmatch(file_relpath, rule.file_glob):
        return False
    if rule.imports_any:
        text = source.decode("utf-8", errors="replace")
        if not any(imp in text for imp in rule.imports_any):
            return False
    return True


def _matches_for(rule: Rule, root: TSNode) -> list[dict[str, list[TSNode]]]:
    cursor = QueryCursor(rule.query)
    matches = cursor.matches(root)
    # matches is list[(pattern_index, dict[capture_name, list[Node]])]
    out: list[dict[str, list[TSNode]]] = []
    for _pi, caps in matches:
        out.append(caps)
    return out


def _build_capture_ctx(captures: dict[str, list[TSNode]]) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    for name, nodes in captures.items():
        if not nodes:
            continue
        ctx[name] = _capture_dict(nodes[0])
    return ctx


def _body_contains_ok(body_contains: list[str], anchor_text: str) -> bool:
    return all(s in anchor_text for s in body_contains)


def _anchor_node(captures: dict[str, list[TSNode]]) -> TSNode | None:
    """First capture's first node is treated as the anchor for body_contains / sub_rules."""
    for name in captures:
        nodes = captures[name]
        if nodes:
            return nodes[0]
    return None


def execute_rule(
    rule: Rule,
    root: TSNode,
    file_relpath: str,
    graph: Graph,
    metrics: ExecutionMetrics,
    parent_ctx: dict[str, Any] | None = None,
    errors_sink: list[dict[str, str]] | None = None,
) -> None:
    """Run `rule` against `root` (whole-tree or anchored sub-tree)."""
    try:
        matches = _matches_for(rule, root)
    except Exception as exc:  # pragma: no cover - defensive
        metrics.errors += 1
        if errors_sink is not None:
            errors_sink.append({
                "pack": rule.pack, "rule_id": rule.id, "file": file_relpath,
                "error": f"query execution failed: {exc}",
            })
        return

    for caps in matches:
        ctx = _build_capture_ctx(caps)
        anchor = _anchor_node(caps)
        if anchor is None:
            continue
        anchor_text = _node_text(anchor)

        if not _where_passes(rule.where, ctx):
            continue
        if not _body_contains_ok(rule.body_contains, anchor_text):
            continue

        ctx["file"] = file_relpath
        if parent_ctx is not None:
            # Expose parent context under `{parent.*}` (drop deeper ancestors to
            # keep chain short; sub-sub-rules can still see their immediate parent).
            ctx["parent"] = {k: v for k, v in parent_ctx.items() if k != "parent"}

        this_node_dict: dict[str, Any] | None = None

        for emit in rule.emits:
            try:
                if emit.kind == "node":
                    spec = emit.spec
                    id_template = spec["id"]
                    rendered_id_key = render(id_template, ctx)
                    node_id = stable_node_id(
                        rule_id=rule.id,
                        file_relpath=file_relpath,
                        canonical_text=rendered_id_key,
                        line_start=anchor.start_point[0] + 1,
                    )
                    properties: dict[str, Any] = {
                        "file": file_relpath,
                        "line": anchor.start_point[0] + 1,
                        "line_end": anchor.end_point[0] + 1,
                        "confidence": "high",
                    }
                    for k, v in (spec.get("properties") or {}).items():
                        properties[k] = render(v, ctx) if isinstance(v, str) else v
                    properties["provenance"] = {
                        "pack": rule.pack,
                        "rule_id": rule.id,
                        "engine_version": __version__,
                    }
                    node = Node(id=node_id, label=spec["label"], properties=properties)
                    graph.add_node(node)
                    metrics.nodes_emitted += 1
                    this_node_dict = {
                        "id": node_id,
                        "label": spec["label"],
                        "line": properties["line"],
                    }
                    ctx["this"] = this_node_dict
                elif emit.kind == "edge":
                    spec = emit.spec
                    from_id = render(spec["from"], ctx)
                    to_id = render(spec["to"], ctx)
                    edge_props: dict[str, Any] = {
                        "confidence": "high",
                    }
                    for k, v in (spec.get("properties") or {}).items():
                        edge_props[k] = render(v, ctx) if isinstance(v, str) else v
                    edge_props["provenance"] = {
                        "pack": rule.pack,
                        "rule_id": rule.id,
                        "engine_version": __version__,
                    }
                    graph.add_edge(Edge(
                        type=spec["type"],
                        from_id=from_id,
                        to_id=to_id,
                        properties=edge_props,
                    ))
                    metrics.edges_emitted += 1
            except Exception as exc:
                metrics.errors += 1
                if errors_sink is not None:
                    errors_sink.append({
                        "pack": rule.pack, "rule_id": rule.id, "file": file_relpath,
                        "error": f"emit failed: {exc}",
                    })

        # Recurse into sub-rules using anchor as new query root + child ctx
        if rule.sub_rules:
            child_parent_ctx = dict(ctx)
            for sub in rule.sub_rules:
                execute_rule(sub, anchor, file_relpath, graph, metrics,
                             parent_ctx=child_parent_ctx, errors_sink=errors_sink)
