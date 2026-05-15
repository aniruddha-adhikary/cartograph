from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .schema import validate_lens_specs
from .views import unique_paths

LensResolver = Callable[[str], dict[str, Any]]


def load_lens_specs(
    workspace: Path | None = None,
    lenses_dir: Path | list[Path] | None = None,
) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    candidates: list[Path] = []
    if workspace:
        candidates.extend(sorted((workspace / ".cartograph" / "lenses").glob("*.json")))
    if lenses_dir:
        lens_dirs_value = [lenses_dir] if isinstance(lenses_dir, Path) else lenses_dir
        for item in lens_dirs_value:
            candidates.extend(sorted(item.glob("*.json")))
    for path in unique_paths(candidates):
        overlay = json.loads(path.read_text(encoding="utf-8"))
        validate_lens_specs(overlay, name=str(path))
        specs.update(overlay)
        validate_lens_specs(specs, name="merged:lenses")
    return specs


def run_lens_spec(
    graph: dict[str, Any],
    name: str,
    spec: dict[str, Any],
    _resolve_lens: LensResolver,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if spec["kind"] != "query":
        raise ValueError(f"configured lenses must use kind=query: {name}")
    query = normalize_query(spec["query"])
    merged_params = {**spec.get("params", {}), **(params or {})}
    result = run_kuzu_query_subset(graph, query, merged_params)
    validate_return_types(result["rows"], spec.get("returns", {}))
    return {
        "nodes": result["nodes"],
        "edges": result["edges"],
        "rows": result["rows"],
        "mode": "kuzu-query",
        "anchors": [name],
        "query": query,
        "returns": spec.get("returns", {}),
    }


def normalize_query(query: str | list[str]) -> str:
    if isinstance(query, list):
        query = "\n".join(query)
    return "\n".join(line.strip() for line in query.strip().splitlines() if line.strip())


def run_kuzu_query_subset(graph: dict[str, Any], query: str, params: dict[str, Any]) -> dict[str, Any]:
    clauses = parse_query(query)
    validate_references(graph, clauses)
    bindings: list[dict[str, Any]] = [{}]
    for clause in clauses["matches"]:
        next_bindings = match_clause(graph, bindings, clause)
        if clause["optional"] and not next_bindings:
            next_bindings = bindings
        bindings = next_bindings
    bindings = [
        binding
        for binding in bindings
        if all(condition_matches(binding, condition, params) for condition in clauses["where"])
    ]
    rows = [project_row(binding, clauses["return"]) for binding in bindings]
    nodes, edges = projected_graph(rows)
    return {"rows": rows, "nodes": nodes, "edges": edges}


def validate_return_types(rows: list[dict[str, Any]], returns: dict[str, str]) -> None:
    for var, expected in returns.items():
        for row in rows:
            value = row.get(var)
            if value is None:
                continue
            actual = (
                value.get("type")
                if isinstance(value, dict) and "type" in value
                else value.get("label")
                if isinstance(value, dict)
                else None
            )
            if actual != expected:
                raise ValueError(f"lens return {var} expected {expected}, got {actual}")


def parse_query(query: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    where: list[str] = []
    returns: list[str] = []
    for line in query.splitlines():
        upper = line.upper()
        if upper.startswith("MATCH "):
            matches.append({"optional": False, "pattern": line[6:].strip()})
            continue
        if upper.startswith("OPTIONAL MATCH "):
            matches.append({"optional": True, "pattern": line[15:].strip()})
            continue
        if upper.startswith("WHERE "):
            where.extend(split_conditions(line[6:].strip()))
            continue
        if upper.startswith("RETURN "):
            returns = [item.strip() for item in line[7:].split(",") if item.strip()]
            continue
        raise ValueError(f"unsupported Kuzu lens clause: {line}")
    if not returns:
        raise ValueError("Kuzu lens query must include RETURN")
    return {"matches": matches, "where": where, "return": returns}


def split_conditions(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s+AND\s+", value, flags=re.IGNORECASE) if part.strip()]


def validate_references(graph: dict[str, Any], clauses: dict[str, Any]) -> None:
    labels = {node.get("label") for node in graph.get("nodes", [])}
    edge_types = {edge.get("type") for edge in graph.get("edges", [])}
    for clause in clauses["matches"]:
        parsed = parse_pattern(clause["pattern"])
        for node_var, node_label in parsed["nodes"]:
            if node_label and node_label not in labels:
                raise ValueError(f"unknown node label in lens query: {node_label} ({node_var})")
        rel = parsed.get("rel")
        if rel and rel["type"] and rel["type"] not in edge_types:
            raise ValueError(f"unknown relationship type in lens query: {rel['type']}")


def match_clause(graph: dict[str, Any], bindings: list[dict[str, Any]], clause: dict[str, Any]) -> list[dict[str, Any]]:
    pattern = parse_pattern(clause["pattern"])
    if pattern["kind"] == "node":
        var, label = pattern["nodes"][0]
        candidates = [node for node in graph.get("nodes", []) if not label or node.get("label") == label]
        return join_candidates(bindings, var, candidates)

    left_var, left_label = pattern["nodes"][0]
    right_var, right_label = pattern["nodes"][1]
    rel = pattern["rel"]
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    output: list[dict[str, Any]] = []
    for binding in bindings:
        for edge in graph.get("edges", []):
            if rel["type"] and edge.get("type") != rel["type"]:
                continue
            source = nodes.get(edge.get("from"))
            target = nodes.get(edge.get("to"))
            if not source or not target:
                continue
            pairs = [(source, target)]
            if rel["direction"] == "left":
                pairs = [(target, source)]
            if rel["direction"] == "undirected":
                pairs = [(source, target), (target, source)]
            for left, right in pairs:
                if left_label and left.get("label") != left_label:
                    continue
                if right_label and right.get("label") != right_label:
                    continue
                merged = bind_item(binding, left_var, left)
                if merged is None:
                    continue
                merged = bind_item(merged, right_var, right)
                if merged is None:
                    continue
                if rel["var"]:
                    merged = bind_item(merged, rel["var"], edge)
                    if merged is None:
                        continue
                output.append(merged)
    return output


def parse_pattern(pattern: str) -> dict[str, Any]:
    node_only = re.fullmatch(r"\((?P<var>[A-Za-z_][A-Za-z0-9_]*)(?::(?P<label>[A-Za-z_][A-Za-z0-9_]*))?\)", pattern)
    if node_only:
        return {"kind": "node", "nodes": [(node_only.group("var"), node_only.group("label"))]}

    pattern_re = re.compile(
        r"^\((?P<left_var>[A-Za-z_][A-Za-z0-9_]*)(?::(?P<left_label>[A-Za-z_][A-Za-z0-9_]*))?\)"
        r"\s*(?P<left_arrow><)?-\s*"
        r"\[(?P<relvar>[A-Za-z_][A-Za-z0-9_]*)?(?::(?P<reltype>[A-Za-z_][A-Za-z0-9_]*))?\]"
        r"\s*-(?P<right_arrow>>)?\s*"
        r"\((?P<right_var>[A-Za-z_][A-Za-z0-9_]*)(?::(?P<right_label>[A-Za-z_][A-Za-z0-9_]*))?\)$"
    )
    match = pattern_re.fullmatch(pattern)
    if not match:
        raise ValueError(f"unsupported Kuzu lens pattern: {pattern}")
    direction = "right"
    if match.group("left_arrow"):
        direction = "left"
    if not match.group("left_arrow") and not match.group("right_arrow"):
        direction = "undirected"
    return {
        "kind": "relationship",
        "nodes": [
            (match.group("left_var"), match.group("left_label")),
            (match.group("right_var"), match.group("right_label")),
        ],
        "rel": {"var": match.group("relvar"), "type": match.group("reltype"), "direction": direction},
    }


def join_candidates(bindings: list[dict[str, Any]], var: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for binding in bindings:
        for candidate in candidates:
            merged = bind_item(binding, var, candidate)
            if merged is not None:
                output.append(merged)
    return output


def bind_item(binding: dict[str, Any], var: str, item: dict[str, Any]) -> dict[str, Any] | None:
    existing = binding.get(var)
    if existing and existing.get("id") != item.get("id"):
        return None
    return {**binding, var: item}


def condition_matches(binding: dict[str, Any], condition: str, params: dict[str, Any]) -> bool:
    match = re.fullmatch(
        r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)\.(?P<prop>[A-Za-z_][A-Za-z0-9_]*)\s+"
        r"(?P<op>CONTAINS|STARTS WITH|ENDS WITH|=)\s+(?P<value>.+)",
        condition,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"unsupported WHERE condition: {condition}")
    item = binding.get(match.group("var"), {})
    actual = str(item.get(match.group("prop"), ""))
    expected = literal_value(match.group("value"), params)
    op = match.group("op").upper()
    if op == "CONTAINS":
        return str(expected) in actual
    if op == "STARTS WITH":
        return actual.startswith(str(expected))
    if op == "ENDS WITH":
        return actual.endswith(str(expected))
    return actual == str(expected)


def literal_value(value: str, params: dict[str, Any]) -> Any:
    value = value.strip()
    if value.startswith("$"):
        return params.get(value[1:])
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        return value[1:-1]
    return value


def project_row(binding: dict[str, Any], returns: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for item in returns:
        if "." in item:
            var, prop = item.split(".", 1)
            row[item] = binding.get(var, {}).get(prop)
        else:
            row[item] = binding.get(item)
    return row


def projected_graph(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        for value in row.values():
            if not isinstance(value, dict):
                continue
            if "type" in value and "from" in value and "to" in value:
                edges[(str(value.get("type")), str(value.get("from")), str(value.get("to")))] = value
            elif "label" in value and "id" in value:
                nodes[value["id"]] = value
    return list(nodes.values()), list(edges.values())
