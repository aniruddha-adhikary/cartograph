from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .engine import _resolve_template, run_source_lens
from .graph import Graph
from .lens_schema import load_builtin_lenses, load_lens_dir
from .models import Edge, Node, SchemaRegistry


def load_all_lenses(
    overlay_dirs: list[Path] | None = None,
) -> list[dict[str, Any]]:
    lenses = load_builtin_lenses()
    names = {l["name"] for l in lenses}
    for directory in overlay_dirs or []:
        for lens in load_lens_dir(directory):
            if lens["name"] in names:
                lenses = [l for l in lenses if l["name"] != lens["name"]]
            lenses.append(lens)
            names.add(lens["name"])
    return lenses


def source_lenses(lenses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [l for l in lenses if l["scope"] == "source"]


def lenses_for_file(
    lenses: list[dict[str, Any]], rel_path: str,
) -> list[dict[str, Any]]:
    matching = []
    for lens in lenses:
        if lens["scope"] != "source":
            continue
        patterns = lens["match"].get("files", [])
        filename = Path(rel_path).name
        if any(fnmatch(filename, p) or fnmatch(rel_path, p) for p in patterns):
            matching.append(lens)
    return matching


def run_lenses_on_file(
    lenses: list[dict[str, Any]],
    rel_path: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    all_nodes: list[Node] = []
    all_edges: list[Edge] = []
    for lens in lenses_for_file(lenses, rel_path):
        nodes, edges = run_source_lens(lens, rel_path, content, service=service)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
    return all_nodes, all_edges


def run_resolve_lenses(lenses: list[dict[str, Any]], graph: Graph) -> int:
    resolve = [l for l in lenses if l.get("scope") == "resolve"]
    resolved = 0
    for node in graph.nodes:
        for lens in resolve:
            match = lens["match"]
            if node.get("label") != match.get("label"):
                continue
            # A4: optional where: filter — AND across keys
            where = match.get("where") or {}
            if any(node.get(k) != v for k, v in where.items()):
                continue
            # Support both new "from" and legacy "field" key for the source prop.
            field = match.get("from") or match.get("field", "")
            value = str(node.get(field, ""))
            if not value:
                continue
            set_block = lens.get("set", {}) or {}
            if not set_block:
                continue
            # Try patterns: list first (preferred), then fall back to a single pattern.
            patterns = match.get("patterns")
            if patterns is None:
                single = match.get("pattern")
                patterns = [{"regex": single}] if single else []
            m = None
            for pat in patterns:
                regex = pat.get("regex") if isinstance(pat, dict) else pat
                if not regex:
                    continue
                m = re.search(regex, value)
                if m:
                    break
            if not m:
                continue
            captures = m.groupdict()
            wrote_any = False
            for key, template in set_block.items():
                # A3: per-key skip — only skip keys that are already non-empty.
                if node.get(key):
                    continue
                # A2: use engine._resolve_template for fallback chain support.
                result = _resolve_template(template, captures)
                if result:
                    node[key] = result
                    wrote_any = True
            if wrote_any:
                resolved += 1
    return resolved


def build_schema_registry(lenses: list[dict[str, Any]]) -> SchemaRegistry:
    registry = SchemaRegistry()
    for lens in lenses:
        if lens.get("scope") not in ("source",):
            continue
        emit = lens.get("emit", {})
        label = emit.get("label")
        schema = emit.get("schema", {})
        if label and schema:
            registry.register_node(label, schema)
    return registry
