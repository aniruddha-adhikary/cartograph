from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .discovery import discover_service_roots, service_config, service_name
from .graph import Graph
from .lens_runner import build_schema_registry, load_all_lenses, run_lenses_on_file, run_resolve_lenses
from .linkers import dedup_call_sites, dedup_edges, load_service_registry, run_linkers
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
    ".xml", ".jsp", ".jspx", ".tag", ".tld",
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

    run_resolve_lenses(lenses, merged)
    _apply_resolve_hints(merged, workspace / "resolve-hints.json")
    registry = load_service_registry(registry_path or workspace / "service-registry.yaml")
    run_linkers(merged, service_contexts, registry)
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


def _excluded(rel: str, extra_patterns: list[str] | None = None) -> bool:
    parts = rel.split("/")
    if any(part in {"node_modules", "target", "build", "dist", "__tests__", "tests"} for part in parts):
        return True
    patterns = [*CORE_EXCLUDES, *(extra_patterns or [])]
    return any(fnmatch(rel, p) or fnmatch(Path(rel).name, p) for p in patterns)
