from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from .schema import validate_view_specs


def load_view_specs(
    workspace: Path | None = None,
    views_dir: Path | list[Path] | None = None,
) -> dict[str, Any]:
    specs = json.loads(resources.files("cartograph").joinpath("views/default.json").read_text(encoding="utf-8"))
    validate_view_specs(specs, name="bundled:views")
    candidates: list[Path] = []
    if workspace:
        candidates.extend(sorted((workspace / ".cartograph" / "views").glob("*.json")))
    if views_dir:
        view_dirs_value = [views_dir] if isinstance(views_dir, Path) else views_dir
        for item in view_dirs_value:
            candidates.extend(sorted(item.glob("*.json")))
    candidates = unique_paths(candidates)
    for path in candidates:
        overlay = json.loads(path.read_text(encoding="utf-8"))
        validate_view_specs(overlay, name=str(path))
        specs.update(overlay)
        validate_view_specs(specs, name="merged:views")
    return specs


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def run_view(graph: dict[str, Any], view: dict[str, Any], params: dict[str, Any] | None = None) -> Any:
    params = params or {}
    kind = view.get("kind")
    if kind == "nodes":
        return node_view(graph, view, params)
    if kind == "edges":
        return edge_view(graph, view, params)
    if kind == "group_edges":
        return group_edges_view(graph, view, params)
    raise ValueError(f"unsupported view kind: {kind}")


def node_view(graph: dict[str, Any], view: dict[str, Any], params: dict[str, Any]) -> list[dict[str, Any]]:
    items = list(graph.get("nodes", []))
    if view.get("label"):
        items = [item for item in items if item.get("label") == view["label"]]
    items = filter_items(items, view.get("where", {}), params)
    items = filter_items(items, params)
    return sort_items(items, view.get("sort", []))


def edge_view(graph: dict[str, Any], view: dict[str, Any], params: dict[str, Any]) -> list[dict[str, Any]]:
    items = list(graph.get("edges", []))
    if view.get("edge_type"):
        items = [item for item in items if item.get("type") == view["edge_type"]]
    if "cross_repo" in view:
        items = [item for item in items if item.get("cross_repo") is view["cross_repo"]]
    items = filter_items(items, view.get("where", {}), params)
    if params.get("type"):
        items = [item for item in items if item.get("type") == params["type"]]
    return sort_items(items, view.get("sort", []))


def group_edges_view(
    graph: dict[str, Any], view: dict[str, Any], params: dict[str, Any]
) -> dict[str, dict[str, list[Any]]]:
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    edges = edge_view(
        graph, {"kind": "edges", "edge_type": view.get("edge_type"), "where": view.get("where", {})}, params
    )
    result: dict[str, dict[str, list[Any]]] = {}
    group_spec = view["group_by"]
    fields = view.get("fields", {})
    for edge in edges:
        group_node = nodes.get(edge[group_spec["side"]])
        if not group_node:
            continue
        group_key = group_node.get(group_spec["property"])
        if group_key is None:
            continue
        bucket = result.setdefault(str(group_key), {name: [] for name in fields})
        for name, spec in fields.items():
            node = nodes.get(edge[spec["side"]])
            if node and spec["property"] in node:
                bucket[name].append(node[spec["property"]])
    return {
        key: {name: sorted(set(values)) for name, values in bucket.items()} for key, bucket in sorted(result.items())
    }


def filter_items(
    items: list[dict[str, Any]], filters: dict[str, Any], params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    params = params or {}
    output = []
    for item in items:
        matched = True
        for key, expected in filters.items():
            if expected is None:
                continue
            if isinstance(expected, str) and expected.startswith("$"):
                expected = params.get(expected[1:])
            if expected is not None and item.get(key) != expected:
                matched = False
                break
        if matched:
            output.append(item)
    return output


def sort_items(items: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    if not keys:
        return items
    return sorted(items, key=lambda item: tuple(str(item.get(key, "")) for key in keys))
