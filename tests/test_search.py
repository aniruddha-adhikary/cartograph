from __future__ import annotations

from cartograph.search import search, search_via_lens


def _sample_graph() -> dict:
    return {
        "nodes": [
            {"id": "a:1", "label": "Endpoint", "service": "orders", "path": "/api/orders", "http_method": "GET", "handler": "OrderController.list"},
            {"id": "a:2", "label": "Endpoint", "service": "orders", "path": "/api/orders/{id}", "http_method": "GET", "handler": "OrderController.get"},
            {"id": "b:1", "label": "Endpoint", "service": "users", "path": "/api/users", "http_method": "GET", "handler": "UserController.list"},
            {"id": "c:1", "label": "KafkaProducer", "service": "orders", "topic": "order-events", "message_role": "producer"},
            {"id": "d:1", "label": "HttpCall", "service": "users", "url": "http://orders-service/api/orders"},
        ],
        "edges": [],
    }


def test_search_exact_match() -> None:
    result = search(_sample_graph(), "/api/orders")
    assert result["mode"] == "exact"
    assert result["count"] >= 1
    paths = [n.get("path") or n.get("url", "") for n in result["nodes"]]
    assert any("/api/orders" in p for p in paths)


def test_search_by_label() -> None:
    result = search(_sample_graph(), "orders", label="KafkaProducer")
    assert result["count"] >= 1
    assert all(n["label"] == "KafkaProducer" for n in result["nodes"])


def test_search_scored_fallback() -> None:
    result = search(_sample_graph(), "UserController")
    assert result["count"] >= 1
    handlers = [n.get("handler", "") for n in result["nodes"]]
    assert any("UserController" in h for h in handlers)


def test_search_no_match() -> None:
    result = search(_sample_graph(), "zzz_nonexistent_zzz")
    assert result["count"] == 0
    assert result["mode"] == "no-match"


def test_search_via_lens_finds_endpoints_by_path() -> None:
    result = search_via_lens(_sample_graph(), "/api/orders", label="Endpoint", field="path")
    assert result["mode"] == "lens"
    assert result["count"] >= 1
    assert all(n["label"] == "Endpoint" for n in result["nodes"])
    assert any("/api/orders" in n.get("path", "") for n in result["nodes"])


def test_search_via_lens_no_match() -> None:
    result = search_via_lens(_sample_graph(), "nonexistent", label="Endpoint", field="path")
    assert result["count"] == 0


def test_search_no_synonym_dependency() -> None:
    result = search(_sample_graph(), "automobile")
    assert result["mode"] == "no-match"
    assert result["count"] == 0
