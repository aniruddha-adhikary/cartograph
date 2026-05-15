from __future__ import annotations

from cartograph.graph import Graph
from cartograph.models import Edge, Node, SchemaRegistry


def test_graph_accepts_typed_node() -> None:
    g = Graph()
    n = Node(
        id="svc:f:1:abc", label="Endpoint", service="svc", file="f.java",
        line=1, source="lens:x", confidence="high", props={"path": "/orders"},
    )
    result = g.add_node(n)
    assert result["id"] == "svc:f:1:abc"
    assert result["path"] == "/orders"
    assert len(g.nodes) == 1


def test_graph_accepts_typed_edge() -> None:
    g = Graph()
    e = Edge(
        type="CROSSES_TIER", from_id="a", to_id="b",
        source="lens:x", confidence="high", props={},
    )
    result = g.add_edge(e)
    assert result["from"] == "a"
    assert result["to"] == "b"
    assert len(g.edges) == 1


def test_graph_to_dict_includes_schema_when_non_empty() -> None:
    g = Graph()
    g.schema.register_node("Endpoint", {"path": "string", "http_method": "string"})
    d = g.to_dict()
    assert "schema" in d["meta"]
    assert d["meta"]["schema"]["node_labels"]["Endpoint"]["path"] == "string"


def test_graph_to_dict_omits_schema_when_empty() -> None:
    g = Graph()
    d = g.to_dict()
    assert "schema" not in d["meta"]


def test_graph_from_dict_restores_schema() -> None:
    g = Graph()
    g.schema.register_node("Endpoint", {"path": "string"})
    g.schema.register_edge("CROSSES_TIER", {"from_service": "string"})
    d = g.to_dict()
    restored = Graph.from_dict(d)
    assert restored.schema.node_labels["Endpoint"] == {"path": "string"}
    assert restored.schema.edge_types["CROSSES_TIER"] == {"from_service": "string"}


def test_graph_from_dict_without_schema_field() -> None:
    d = {"meta": {"version": 1}, "nodes": [], "edges": []}
    g = Graph.from_dict(d)
    assert g.schema.node_labels == {}
    assert g.meta["version"] == 1
