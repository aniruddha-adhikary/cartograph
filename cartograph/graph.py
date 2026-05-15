from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Edge as TypedEdge
from .models import Node as TypedNode
from .models import SchemaRegistry

CONFIDENCE = {"high", "medium", "low"}


@dataclass
class Graph:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    schema: SchemaRegistry = field(default_factory=SchemaRegistry)

    def add_node(self, node: dict[str, Any] | TypedNode) -> dict[str, Any]:
        if isinstance(node, TypedNode):
            node = node.to_dict()
        if node.get("confidence") not in CONFIDENCE:
            raise ValueError(f"invalid node confidence: {node.get('confidence')}")
        self.nodes.append(node)
        return node

    def add_edge(self, edge: dict[str, Any] | TypedEdge) -> dict[str, Any]:
        if isinstance(edge, TypedEdge):
            edge = edge.to_dict()
        if edge.get("confidence") not in CONFIDENCE:
            raise ValueError(f"invalid edge confidence: {edge.get('confidence')}")
        self.edges.append(edge)
        return edge

    def to_dict(self) -> dict[str, Any]:
        meta = dict(self.meta)
        schema_dict = self.schema.to_dict()
        if schema_dict["node_labels"] or schema_dict["edge_types"]:
            meta["schema"] = schema_dict
        return {"meta": meta, "nodes": self.nodes, "edges": self.edges}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Graph:
        meta = dict(data.get("meta", {}))
        schema = SchemaRegistry.from_dict(meta.pop("schema", {}))
        return cls(
            nodes=list(data.get("nodes", [])),
            edges=list(data.get("edges", [])),
            meta=meta,
            schema=schema,
        )


def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return edge["type"], edge["from"], edge["to"]
