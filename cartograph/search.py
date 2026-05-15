from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .graph_engine import run_graph_lens


def search(
    graph_data: dict[str, Any],
    query: str,
    limit: int = 10,
    label: str | None = None,
) -> dict[str, Any]:
    nodes = graph_data.get("nodes", [])
    if label:
        nodes = [n for n in nodes if n.get("label") == label]

    exact = _exact_matches(nodes, query)
    if exact:
        return _response(exact[:limit], query, mode="exact")

    scored = _scored_matches(nodes, query)
    if scored:
        top = sorted(scored, key=lambda x: -x[1])[:limit]
        return _response(
            [n for n, _ in top], query, mode="scored",
        )

    return _response([], query, mode="no-match")


def search_via_lens(
    graph_data: dict[str, Any],
    query: str,
    label: str = "Endpoint",
    field: str = "path",
) -> dict[str, Any]:
    lens = {
        "name": "dynamic-search",
        "scope": "graph",
        "match": {
            "query": f"MATCH (n:{label})\nWHERE n.{field} CONTAINS $query\nRETURN n",
            "params": {"query": query},
        },
        "emit": {"returns": {"n": label}},
    }
    result = run_graph_lens(lens, graph_data)
    found = [row["n"] for row in result["rows"] if "n" in row]
    return _response(found, query, mode="lens")


def _exact_matches(nodes: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    lowered = query.lower()
    return [n for n in nodes if lowered in _searchable_text(n).lower()]


def _scored_matches(
    nodes: list[dict[str, Any]], query: str,
) -> list[tuple[dict[str, Any], float]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    results = []
    for node in nodes:
        score = _score(node, query_tokens, query.lower())
        if score > 0:
            results.append((node, score))
    return results


def _score(node: dict[str, Any], query_tokens: list[str], phrase: str) -> float:
    score = 0.0
    for field, weight, text in _weighted_fields(node):
        lowered = text.lower()
        if phrase in lowered:
            score += 10 * weight
        field_tokens = Counter(_tokens(text))
        overlap = sum(field_tokens.get(t, 0) for t in query_tokens)
        if overlap:
            score += overlap * weight
    return score


def _weighted_fields(node: dict[str, Any]) -> list[tuple[str, float, str]]:
    topics = " ".join(str(t) for t in node.get("topics", []))
    return [
        ("path", 5.0, str(node.get("path", ""))),
        ("topic", 5.0, " ".join([str(node.get("topic", "")), topics])),
        ("handler", 4.0, str(node.get("handler", ""))),
        ("name", 3.0, str(node.get("name", ""))),
        ("service", 2.0, str(node.get("service", ""))),
        ("label", 1.5, str(node.get("label", ""))),
        ("file", 1.0, str(node.get("file", ""))),
    ]


def _searchable_text(node: dict[str, Any]) -> str:
    values = []
    for value in node.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value)
    return " ".join(values)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", text)]


def _response(
    nodes: list[dict[str, Any]], query: str, mode: str,
) -> dict[str, Any]:
    return {
        "query": query,
        "mode": mode,
        "count": len(nodes),
        "nodes": nodes,
    }
