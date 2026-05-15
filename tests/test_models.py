from __future__ import annotations

from cartograph.models import Edge, Node, SchemaRegistry


def test_node_to_dict_flattens_props() -> None:
    n = Node(
        id="svc:f:1:abc", label="Endpoint", service="svc", file="f.java",
        line=1, source="lens:spring-rest", confidence="high",
        props={"path": "/orders", "http_method": "GET", "handler": "OrderCtrl.get"},
    )
    d = n.to_dict()
    assert d["id"] == "svc:f:1:abc"
    assert d["path"] == "/orders"
    assert d["http_method"] == "GET"
    assert "props" not in d


def test_node_from_dict_splits_universal_fields() -> None:
    d = {
        "id": "svc:f:1:abc", "label": "Endpoint", "service": "svc", "file": "f.java",
        "line": 1, "source": "lens:x", "confidence": "high", "path": "/orders",
    }
    n = Node.from_dict(d)
    assert n.label == "Endpoint"
    assert n.props == {"path": "/orders"}


def test_edge_to_dict_uses_from_and_to_keys() -> None:
    e = Edge(
        type="CROSSES_TIER", from_id="a", to_id="b", source="lens:x", confidence="high",
        props={"from_service": "svc1", "to_service": "svc2"},
    )
    d = e.to_dict()
    assert d["from"] == "a"
    assert d["to"] == "b"
    assert d["from_service"] == "svc1"
    assert "from_id" not in d
    assert "to_id" not in d


def test_edge_from_dict_maps_from_to_to_from_id_to_id() -> None:
    d = {"type": "HANDLES", "from": "a", "to": "b", "source": "x", "confidence": "high"}
    e = Edge.from_dict(d)
    assert e.from_id == "a"
    assert e.to_id == "b"


def test_node_get_reads_from_props() -> None:
    n = Node(
        id="x", label="Endpoint", service="s", file="f", line=1,
        source="src", confidence="high", props={"path": "/foo"},
    )
    assert n.get("path") == "/foo"
    assert n.get("missing", "default") == "default"


def test_schema_registry_accumulates_labels() -> None:
    reg = SchemaRegistry()
    reg.register_node("Endpoint", {"path": "string", "http_method": "string"})
    reg.register_node("Endpoint", {"handler": "string"})
    assert reg.node_labels["Endpoint"] == {"path": "string", "http_method": "string", "handler": "string"}


def test_schema_registry_round_trips() -> None:
    reg = SchemaRegistry()
    reg.register_node("Endpoint", {"path": "string"})
    reg.register_edge("CROSSES_TIER", {"from_service": "string"})
    d = reg.to_dict()
    restored = SchemaRegistry.from_dict(d)
    assert restored.node_labels == reg.node_labels
    assert restored.edge_types == reg.edge_types
