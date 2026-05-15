from __future__ import annotations

from cartograph.graph_engine import run_graph_lens


def _sample_graph() -> dict:
    return {
        "nodes": [
            {"id": "a:f:1:x", "label": "Endpoint", "service": "svc-a", "path": "/orders", "http_method": "GET"},
            {"id": "b:f:2:y", "label": "HttpCall", "service": "svc-b", "host": "svc-a", "path": "/orders"},
            {"id": "c:f:3:z", "label": "KafkaProducer", "service": "svc-a", "message_role": "producer", "topic": "events"},
            {"id": "d:f:4:w", "label": "KafkaConsumer", "service": "svc-c", "message_role": "consumer", "topic": "events"},
        ],
        "edges": [
            {"type": "CROSSES_TIER", "from": "b:f:2:y", "to": "a:f:1:x", "confidence": "high"},
            {"type": "KAFKA_DELIVERS", "from": "c:f:3:z", "to": "d:f:4:w", "confidence": "high"},
        ],
    }


def test_graph_lens_matches_node_pattern() -> None:
    lens = {
        "name": "all-endpoints",
        "scope": "graph",
        "match": {"query": "MATCH (e:Endpoint)\nRETURN e"},
        "emit": {"returns": {"e": "Endpoint"}},
    }
    result = run_graph_lens(lens, _sample_graph())
    assert len(result["rows"]) == 1
    assert result["rows"][0]["e"]["label"] == "Endpoint"
    assert result["mode"] == "kuzu-subset"


def test_graph_lens_matches_relationship_pattern() -> None:
    lens = {
        "name": "cross-tier",
        "scope": "graph",
        "match": {"query": "MATCH (caller:HttpCall)-[e:CROSSES_TIER]->(endpoint:Endpoint)\nRETURN caller, e, endpoint"},
        "emit": {"returns": {"caller": "HttpCall", "e": "CROSSES_TIER", "endpoint": "Endpoint"}},
    }
    result = run_graph_lens(lens, _sample_graph())
    assert len(result["rows"]) == 1
    assert result["rows"][0]["caller"]["label"] == "HttpCall"
    assert result["rows"][0]["endpoint"]["path"] == "/orders"


def test_graph_lens_with_where_clause() -> None:
    lens = {
        "name": "get-endpoints",
        "scope": "graph",
        "match": {
            "query": "MATCH (e:Endpoint)\nWHERE e.http_method = 'GET'\nRETURN e",
        },
        "emit": {"returns": {"e": "Endpoint"}},
    }
    result = run_graph_lens(lens, _sample_graph())
    assert len(result["rows"]) == 1
    assert result["rows"][0]["e"]["http_method"] == "GET"


def test_graph_lens_kafka_bus_view() -> None:
    lens = {
        "name": "kafka-bus",
        "scope": "graph",
        "match": {
            "query": "MATCH (p:KafkaProducer)-[d:KAFKA_DELIVERS]->(c:KafkaConsumer)\nRETURN p, d, c",
        },
        "emit": {"returns": {"p": "KafkaProducer", "d": "KAFKA_DELIVERS", "c": "KafkaConsumer"}},
    }
    result = run_graph_lens(lens, _sample_graph())
    assert len(result["rows"]) == 1
    assert result["rows"][0]["p"]["topic"] == "events"
    assert result["rows"][0]["c"]["topic"] == "events"


def test_graph_lens_with_params() -> None:
    lens = {
        "name": "endpoint-by-path",
        "scope": "graph",
        "match": {
            "query": "MATCH (e:Endpoint)\nWHERE e.path CONTAINS $path\nRETURN e",
            "params": {"path": "/orders"},
        },
        "emit": {"returns": {"e": "Endpoint"}},
    }
    result = run_graph_lens(lens, _sample_graph())
    assert len(result["rows"]) == 1

    result_miss = run_graph_lens(lens, _sample_graph(), params={"path": "/nonexistent"})
    assert len(result_miss["rows"]) == 0


def test_graph_lens_returns_projected_nodes_and_edges() -> None:
    lens = {
        "name": "cross-tier",
        "scope": "graph",
        "match": {"query": "MATCH (c:HttpCall)-[e:CROSSES_TIER]->(ep:Endpoint)\nRETURN c, e, ep"},
        "emit": {"returns": {}},
    }
    result = run_graph_lens(lens, _sample_graph())
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1
