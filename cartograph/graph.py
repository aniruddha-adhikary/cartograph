from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONFIDENCE = {"high", "medium", "low"}


@dataclass
class Graph:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: dict[str, Any]) -> dict[str, Any]:
        if node.get("confidence") not in CONFIDENCE:
            raise ValueError(f"invalid node confidence: {node.get('confidence')}")
        self.nodes.append(node)
        return node

    def add_edge(self, edge: dict[str, Any]) -> dict[str, Any]:
        if edge.get("confidence") not in CONFIDENCE:
            raise ValueError(f"invalid edge confidence: {edge.get('confidence')}")
        self.edges.append(edge)
        return edge

    def to_dict(self) -> dict[str, Any]:
        return {"meta": self.meta, "nodes": self.nodes, "edges": self.edges}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Graph:
        return cls(
            nodes=list(data.get("nodes", [])), edges=list(data.get("edges", [])), meta=dict(data.get("meta", {}))
        )


def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return edge["type"], edge["from"], edge["to"]
