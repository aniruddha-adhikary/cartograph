from __future__ import annotations

import hashlib
from typing import Any

from .graph import Graph
from .query import domain_lenses, graph_version, route_pattern_lenses

PATTERN_LENSES = {
    "pattern.endpoints": lambda graph: [node for node in graph.get("nodes", []) if node.get("label") == "Endpoint"],
    "pattern.controllers": lambda graph: [
        node
        for node in graph.get("nodes", [])
        if node.get("label") == "Service" and "controller" in str(node.get("kind", ""))
    ],
    "pattern.components": lambda graph: [node for node in graph.get("nodes", []) if node.get("label") == "Component"],
    "pattern.message_bus": lambda graph: [
        node for node in graph.get("nodes", []) if node.get("message_role") in {"producer", "consumer"}
    ],
}


def persist_lenses(graph: Graph) -> None:
    data = graph.to_dict()
    version = graph_version(data)
    existing_lens_ids = {node["id"] for node in graph.nodes if node.get("label") == "Lens"}
    existing_contains = {(edge.get("from"), edge.get("to")) for edge in graph.edges if edge.get("type") == "CONTAINS"}

    for lens_name, members in build_lens_members(data).items():
        lens = lens_node(lens_name, members["mode"], members["anchors"], version)
        if lens["id"] not in existing_lens_ids:
            graph.add_node(lens)
            existing_lens_ids.add(lens["id"])
        for member in members["nodes"]:
            key = (lens["id"], member["id"])
            if key in existing_contains:
                continue
            graph.add_edge(
                {
                    "type": "CONTAINS",
                    "from": lens["id"],
                    "to": member["id"],
                    "from_service": lens["service"],
                    "to_service": member.get("service", ""),
                    "cross_repo": False,
                    "confidence": "high",
                    "source": "pack:lens",
                }
            )
            existing_contains.add(key)


def build_lens_members(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for name, selector in PATTERN_LENSES.items():
        output[name] = {"mode": "pattern", "anchors": [name], "nodes": selector(graph)}

    cross_edges = [edge for edge in graph.get("edges", []) if edge.get("type") == "CROSSES_TIER"]
    ids = {edge["from"] for edge in cross_edges} | {edge["to"] for edge in cross_edges}
    output["pattern.cross_tier_calls"] = {
        "mode": "pattern",
        "anchors": ["pattern.cross_tier_calls"],
        "nodes": [node for node in graph.get("nodes", []) if node.get("id") in ids],
    }

    for name, response in {**route_pattern_lenses(graph), **domain_lenses(graph)}.items():
        output[name] = {
            "mode": response.get("mode", "generated"),
            "anchors": response.get("anchors", [name]),
            "nodes": response.get("nodes", []),
        }
    return output


def lens_node(name: str, mode: str, anchors: list[str], version: str) -> dict[str, Any]:
    digest = hashlib.sha1(f"{name}:{mode}:{version}".encode()).hexdigest()[:10]
    return {
        "id": f"cartograph:lens:{digest}",
        "label": "Lens",
        "service": "cartograph",
        "source": "pack:lens",
        "confidence": "high",
        "name": name,
        "mode": mode,
        "anchors": anchors,
        "graph_version": version,
    }
