from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .discovery import discover_service_roots, service_config, service_name
from .graph import Graph
from .lens_runner import build_schema_registry, load_all_lenses, run_lenses_on_file, run_resolve_lenses
from .linkers import (
    apply_constants_to_nodes,
    dedup_call_sites,
    dedup_edges,
    link_cdi_event,
    link_endpoint_param,
    link_entity_relation,
    link_injection,
    load_service_registry,
    run_linkers,
)
from .tree_sitter_strategy import _find_nodes, _get_language, tree_sitter_available
from .util import slug

CORE_EXCLUDES = [
    "src/test/**",
    "tests/**",
    "__tests__/**",
    "*Tests.java",
    "*.test.js",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.js",
    "*.spec.ts",
    "*.spec.tsx",
    "node_modules/**",
    "target/**",
    "build/**",
    "dist/**",
]

SOURCE_EXTS = {
    ".java", ".js", ".jsx", ".ts", ".tsx",
    ".yml", ".yaml", ".properties",
    ".xml", ".jsp", ".jspx", ".tag", ".tld", ".xhtml", ".wsdl",
    ".sql", ".json",
}


def index_workspace(
    workspace: Path,
    registry_path: Path | None = None,
    include_test_paths: bool = False,
    lens_dirs: list[Path] | None = None,
    # Legacy args kept for CLI compat — ignored
    packs_dir: Path | list[Path] | None = None,
) -> Graph:
    workspace = workspace.resolve()
    service_roots = discover_service_roots(workspace)
    lenses = load_all_lenses(overlay_dirs=lens_dirs)
    merged = Graph(meta={"version": 2, "workspace": str(workspace)})
    merged.schema = build_schema_registry(lenses)
    service_contexts: list[_ServiceCtx] = []

    for root in service_roots:
        name = service_name(root)
        config = service_config(root)
        ctx = _ServiceCtx(name=name, root=root, graph=Graph(meta={"service": name}))
        _index_service(ctx, lenses, include_test_paths or bool(config.get("include_test_paths")), config)
        dedup_call_sites(ctx.graph)
        service_contexts.append(ctx)
        merged.nodes.extend(ctx.graph.nodes)
        merged.edges.extend(ctx.graph.edges)

    constants_by_file = _collect_java_constants(service_contexts)
    merged.meta["java_constants"] = {
        f: dict(c) for f, c in constants_by_file.items()
    }
    apply_constants_to_nodes(merged, constants_by_file)

    run_resolve_lenses(lenses, merged)
    _apply_resolve_hints(merged, workspace / "resolve-hints.json")
    registry = load_service_registry(registry_path or workspace / "service-registry.yaml")
    run_linkers(merged, service_contexts, registry)
    link_injection(merged)
    link_entity_relation(merged)
    link_cdi_event(merged)
    link_endpoint_param(merged)
    dedup_edges(merged)

    merged.meta["services"] = sorted(
        {ctx.name for ctx in service_contexts}
        | {n["service"] for n in merged.nodes if "service" in n and n["service"] != "cartograph"}
    )
    merged.meta["node_count"] = len(merged.nodes)
    merged.meta["edge_count"] = len(merged.edges)
    merged.meta["lens_count"] = len(lenses)
    return merged


class _ServiceCtx:
    __slots__ = ("name", "root", "graph", "application_names")

    def __init__(self, name: str, root: Path, graph: Graph) -> None:
        self.name = name
        self.root = root
        self.graph = graph
        self.application_names: set[str] = set()


def _index_service(
    ctx: _ServiceCtx,
    lenses: list[dict[str, Any]],
    include_test_paths: bool,
    config: dict[str, Any],
) -> None:
    for path in sorted(ctx.root.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_EXTS:
            continue
        rel = path.relative_to(ctx.root).as_posix()
        if not include_test_paths and _excluded(rel, config.get("exclude", [])):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        nodes, edges = run_lenses_on_file(lenses, rel, content, service=ctx.name)
        for node in nodes:
            ctx.graph.add_node(node)
        for edge in edges:
            ctx.graph.add_edge(edge)


def _apply_resolve_hints(graph: Graph, hints_path: Path) -> int:
    if not hints_path.exists():
        return 0
    hints = json.loads(hints_path.read_text(encoding="utf-8"))
    applied = 0
    for hint in hints:
        match_spec = hint.get("match", {})
        set_fields = hint.get("set", {})
        for node in graph.nodes:
            if all(node.get(k) == v for k, v in match_spec.items()):
                for k, v in set_fields.items():
                    node[k] = v
                applied += 1
    graph.meta["resolve_hints_applied"] = applied
    return applied


def _collect_java_constants(service_contexts: list[_ServiceCtx]) -> dict[str, dict[str, str]]:
    """Scan every Java file under each service root, extracting
    `public static final String NAME = "value";` declarations.

    Returns a per-file map keyed by relative path (service-root-relative,
    matching node `file` props), containing both qualified `ClassName.NAME`
    and unqualified `NAME` keys -> string value.
    """
    if not tree_sitter_available():
        return {}
    try:
        import tree_sitter as ts
    except ImportError:
        return {}

    out: dict[str, dict[str, str]] = {}
    try:
        language = _get_language("java")
    except Exception:
        return {}
    parser = ts.Parser(language)

    for ctx in service_contexts:
        for path in ctx.root.rglob("*.java"):
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = path.relative_to(ctx.root).as_posix()
            try:
                tree = parser.parse(content.encode("utf-8"))
            except Exception:
                continue
            consts = _extract_string_constants(tree.root_node)
            if consts:
                out[rel] = consts
    return out


def _extract_string_constants(root: Any) -> dict[str, str]:
    """Extract `public static final String NAME = "value";` from each
    class_declaration in the parsed tree. Stores both `ClassName.NAME` and
    bare `NAME` keys.
    """
    result: dict[str, str] = {}
    for cls in _find_nodes(root, "class_declaration"):
        name_node = cls.child_by_field_name("name")
        class_name = name_node.text.decode("utf-8") if name_node else ""
        body = cls.child_by_field_name("body")
        if body is None:
            continue
        for field_decl in body.children:
            if field_decl.type != "field_declaration":
                continue
            mods_text = ""
            type_text = ""
            for ch in field_decl.children:
                if ch.type == "modifiers":
                    mods_text = ch.text.decode("utf-8")
                elif ch.type in ("type_identifier", "generic_type", "scoped_type_identifier"):
                    type_text = ch.text.decode("utf-8")
            if "static" not in mods_text or "final" not in mods_text:
                continue
            if "String" not in type_text:
                continue
            for ch in field_decl.children:
                if ch.type != "variable_declarator":
                    continue
                vname_node = ch.child_by_field_name("name")
                value_node = ch.child_by_field_name("value")
                if vname_node is None or value_node is None:
                    continue
                if value_node.type != "string_literal":
                    continue
                # extract the inner string_fragment
                str_val = ""
                for sc in value_node.children:
                    if sc.type == "string_fragment":
                        str_val = sc.text.decode("utf-8")
                        break
                vname = vname_node.text.decode("utf-8")
                result[vname] = str_val
                if class_name:
                    result[f"{class_name}.{vname}"] = str_val
    return result


def _excluded(rel: str, extra_patterns: list[str] | None = None) -> bool:
    parts = rel.split("/")
    if any(part in {"node_modules", "target", "build", "dist", "__tests__", "tests"} for part in parts):
        return True
    patterns = [*CORE_EXCLUDES, *(extra_patterns or [])]
    return any(fnmatch(rel, p) or fnmatch(Path(rel).name, p) for p in patterns)
