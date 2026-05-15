from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def verify_graph(graph_path: Path, suite_path: Path) -> list[str]:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    errors: list[str] = []

    errors.extend(check_services(nodes, suite.get("services", [])))
    errors.extend(check_duplicate_ids(nodes) if suite.get("no_duplicate_node_ids", False) else [])
    errors.extend(check_no_test_edges(nodes, edges) if suite.get("no_test_path_edges", False) else [])
    errors.extend(check_no_forbidden(nodes, suite.get("forbidden_labels", [])))
    errors.extend(check_min_counts(nodes, edges, suite.get("min_counts", {})))
    errors.extend(check_required_edges(nodes, edges, suite.get("required_edges", [])))
    errors.extend(check_confidence(nodes, edges, suite.get("confidence", {})))
    return errors


def check_services(nodes: list[dict[str, Any]], expected: list[str]) -> list[str]:
    if not expected:
        return []
    found = {n.get("service") for n in nodes}
    return [f"missing service {service}" for service in expected if service not in found]


def check_duplicate_ids(nodes: list[dict[str, Any]]) -> list[str]:
    counts = Counter(n.get("id") for n in nodes)
    return [f"duplicate node id {node_id}" for node_id, count in counts.items() if count > 1]


def check_no_test_edges(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    by_id = {n["id"]: n for n in nodes}
    errors = []
    for item in edges:
        if item.get("type") not in {"KAFKA_DELIVERS", "CROSSES_TIER"}:
            continue
        for endpoint in (item.get("from"), item.get("to")):
            node = by_id.get(endpoint)
            if node and is_test_path(str(node.get("file") or node.get("path") or "")):
                errors.append(f"edge {item['type']} touches excluded test path {node.get('file') or node.get('path')}")
    return errors


def check_no_forbidden(nodes: list[dict[str, Any]], labels: list[str]) -> list[str]:
    forbidden = set(labels)
    return [f"forbidden node label {n['label']} at {n['id']}" for n in nodes if n.get("label") in forbidden]


def check_min_counts(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], counts: dict[str, int]) -> list[str]:
    errors = []
    node_counts = Counter(n["label"] for n in nodes)
    edge_counts = Counter(e["type"] for e in edges)
    for key, expected in counts.items():
        actual = (
            len(nodes)
            if key == "nodes"
            else len(edges)
            if key == "edges"
            else node_counts.get(key, 0) + edge_counts.get(key, 0)
        )
        if actual < expected:
            errors.append(f"{key} count {actual} < {expected}")
    return errors


def check_required_edges(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], required: list[dict[str, Any]]
) -> list[str]:
    by_id = {n["id"]: n for n in nodes}
    errors = []
    for req in required:
        matched = False
        for item in edges:
            if req.get("type") and item.get("type") != req["type"]:
                continue
            if req.get("from_service") and item.get("from_service") != req["from_service"]:
                continue
            if req.get("to_service") and item.get("to_service") != req["to_service"]:
                continue
            from_node = by_id.get(item.get("from"))
            to_node = by_id.get(item.get("to"))
            if req.get("topic") and (not from_node or from_node.get("topic") != req["topic"]):
                continue
            if req.get("path") and (not to_node or to_node.get("path") != req["path"]):
                continue
            matched = True
            break
        if not matched:
            errors.append(f"missing required edge {req}")
    return errors


def check_confidence(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], rules: dict[str, Any]) -> list[str]:
    errors = []
    allowed_low_sources = set(rules.get("allowed_low_sources", []))
    if rules.get("no_unapproved_low", False):
        for item in nodes + edges:
            source = str(item.get("source") or item.get("type") or "")
            if item.get("confidence") == "low" and source not in allowed_low_sources:
                errors.append(f"unapproved low-confidence item {item.get('id') or item.get('type')}")
    return errors


def is_test_path(path: str) -> bool:
    return any(token in path for token in ("src/test/", "tests/", "__tests__/", "Tests.java", ".test.", ".spec."))
