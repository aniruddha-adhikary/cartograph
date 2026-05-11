"""In-memory property graph + deterministic JSON IO."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Node:
    id: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "properties": self.properties}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Node":
        return cls(id=d["id"], label=d["label"], properties=dict(d.get("properties") or {}))


@dataclass
class Edge:
    type: str
    from_id: str
    to_id: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Edge":
        return cls(
            type=d["type"],
            from_id=d["from_id"],
            to_id=d["to_id"],
            properties=dict(d.get("properties") or {}),
        )


class Graph:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._linkers: list[Any] = []

    # mutation
    def add_node(self, node: Node) -> Node:
        existing = self._nodes.get(node.id)
        if existing is None:
            self._nodes[node.id] = node
            return node
        # Merge properties idempotently (later writes win for individual keys)
        merged = dict(existing.properties)
        merged.update(node.properties)
        existing.properties = merged
        return existing

    def add_edge(self, edge: Edge) -> None:
        self._edges.append(edge)

    # access
    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes.values())

    @property
    def edges(self) -> list[Edge]:
        return list(self._edges)

    def by_label(self, label: str) -> list[Node]:
        return [n for n in self._nodes.values() if n.label == label]

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    # deletion (incremental)
    def drop_nodes_from_files(self, files: Iterable[str]) -> None:
        file_set = set(files)
        dropped_ids: set[str] = set()
        for nid, node in list(self._nodes.items()):
            if node.properties.get("file") in file_set:
                dropped_ids.add(nid)
                del self._nodes[nid]
        if dropped_ids:
            self._edges = [
                e for e in self._edges
                if e.from_id not in dropped_ids and e.to_id not in dropped_ids
            ]

    def drop_edges_by_linker(self, linker_name: str) -> None:
        self._edges = [
            e for e in self._edges
            if (e.properties.get("provenance") or {}).get("linker") != linker_name
        ]

    # linkers
    def add_linker(self, linker: Any) -> None:
        self._linkers.append(linker)

    def run_linkers(self) -> None:
        for linker in self._linkers:
            linker.run(self)

    # serialization (deterministic)
    def to_dict(self) -> dict[str, Any]:
        nodes_sorted = sorted(self._nodes.values(), key=lambda n: n.id)
        edges_sorted = sorted(
            self._edges,
            key=lambda e: (e.type, e.from_id, e.to_id, json.dumps(e.properties, sort_keys=True)),
        )
        return {
            "nodes": [n.to_dict() for n in nodes_sorted],
            "edges": [e.to_dict() for e in edges_sorted],
        }

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json_str())

    def to_json_str(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Graph":
        g = cls()
        for n in d.get("nodes", []):
            g.add_node(Node.from_dict(n))
        for e in d.get("edges", []):
            g.add_edge(Edge.from_dict(e))
        return g

    @classmethod
    def from_json(cls, path: str | Path) -> "Graph":
        return cls.from_dict(json.loads(Path(path).read_text()))
