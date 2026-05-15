from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

UNIVERSAL_NODE_FIELDS = {"id", "label", "service", "file", "line", "source", "confidence"}
UNIVERSAL_EDGE_FIELDS = {"type", "from", "to", "from_id", "to_id", "source", "confidence"}


@dataclass
class Node:
    id: str
    label: str
    service: str
    file: str
    line: int
    source: str
    confidence: Literal["high", "medium", "low"]
    props: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "service": self.service,
            "file": self.file, "line": self.line, "source": self.source,
            "confidence": self.confidence, **self.props,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        props = {k: v for k, v in data.items() if k not in UNIVERSAL_NODE_FIELDS}
        return cls(
            id=data["id"], label=data["label"], service=data.get("service", ""),
            file=data.get("file", ""), line=data.get("line", 0),
            source=data.get("source", ""), confidence=data.get("confidence", "high"),
            props=props,
        )


@dataclass
class Edge:
    type: str
    from_id: str
    to_id: str
    source: str
    confidence: Literal["high", "medium", "low"]
    props: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type, "from": self.from_id, "to": self.to_id,
            "source": self.source, "confidence": self.confidence, **self.props,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        props = {k: v for k, v in data.items() if k not in UNIVERSAL_EDGE_FIELDS}
        return cls(
            type=data["type"], from_id=data.get("from", data.get("from_id", "")),
            to_id=data.get("to", data.get("to_id", "")),
            source=data.get("source", ""), confidence=data.get("confidence", "high"),
            props=props,
        )


@dataclass
class SchemaRegistry:
    node_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    edge_types: dict[str, dict[str, str]] = field(default_factory=dict)

    def register_node(self, label: str, schema: dict[str, str]) -> None:
        existing = self.node_labels.get(label, {})
        self.node_labels[label] = {**existing, **schema}

    def register_edge(self, edge_type: str, schema: dict[str, str]) -> None:
        existing = self.edge_types.get(edge_type, {})
        self.edge_types[edge_type] = {**existing, **schema}

    def to_dict(self) -> dict[str, Any]:
        return {"node_labels": self.node_labels, "edge_types": self.edge_types}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchemaRegistry:
        return cls(
            node_labels=data.get("node_labels", {}),
            edge_types=data.get("edge_types", {}),
        )
