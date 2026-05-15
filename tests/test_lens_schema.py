from __future__ import annotations

import json
from pathlib import Path

import pytest

from cartograph.lens_schema import LensValidationError, load_lens_file, validate_lens


def test_valid_source_lens_passes() -> None:
    lens = {
        "name": "spring-rest-endpoint",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "annotation-method",
            "class_annotations": ["@RestController", "@Controller"],
        },
        "emit": {
            "label": "Endpoint",
            "schema": {"path": "string", "http_method": "string"},
            "values": {"path": "{{base_path}}/{{method_path}}", "http_method": "{{http_method}}"},
            "source": "lens:spring-rest-endpoint",
            "confidence": "high",
        },
    }
    validate_lens(lens)


def test_valid_graph_lens_passes() -> None:
    lens = {
        "name": "kafka-bus-view",
        "scope": "graph",
        "match": {"query": "MATCH (p:KafkaProducer)-[d:KAFKA_DELIVERS]->(c:KafkaConsumer) RETURN p, d, c"},
        "emit": {"returns": {"p": "KafkaProducer", "d": "KAFKA_DELIVERS", "c": "KafkaConsumer"}},
    }
    validate_lens(lens)


def test_missing_name_raises() -> None:
    with pytest.raises(LensValidationError, match="name"):
        validate_lens({"scope": "source", "match": {}, "emit": {}})


def test_invalid_scope_raises() -> None:
    with pytest.raises(LensValidationError, match="scope"):
        validate_lens({"name": "x", "scope": "invalid", "match": {}, "emit": {}})


def test_source_lens_requires_files_in_match() -> None:
    with pytest.raises(LensValidationError, match="files"):
        validate_lens({
            "name": "x", "scope": "source",
            "match": {"strategy": "regex"},
            "emit": {"label": "X", "schema": {}, "values": {}, "source": "x", "confidence": "high"},
        })


def test_source_lens_requires_emit_label() -> None:
    with pytest.raises(LensValidationError, match="label"):
        validate_lens({
            "name": "x", "scope": "source",
            "match": {"files": ["*.java"]},
            "emit": {"schema": {}, "values": {}, "source": "x", "confidence": "high"},
        })


def test_graph_lens_requires_query_in_match() -> None:
    with pytest.raises(LensValidationError, match="query"):
        validate_lens({"name": "x", "scope": "graph", "match": {}, "emit": {}})


def test_load_lens_file_loads_list_of_lenses(tmp_path: Path) -> None:
    path = tmp_path / "test.json"
    path.write_text(json.dumps([
        {"name": "a", "scope": "graph", "match": {"query": "MATCH (n) RETURN n"}, "emit": {"returns": {}}},
        {"name": "b", "scope": "graph", "match": {"query": "MATCH (n) RETURN n"}, "emit": {"returns": {}}},
    ]))
    lenses = load_lens_file(path)
    assert [item["name"] for item in lenses] == ["a", "b"]


def test_load_lens_file_loads_single_lens_dict(tmp_path: Path) -> None:
    path = tmp_path / "single.json"
    path.write_text(json.dumps({
        "name": "only", "scope": "graph",
        "match": {"query": "MATCH (n) RETURN n"}, "emit": {"returns": {}},
    }))
    lenses = load_lens_file(path)
    assert len(lenses) == 1
    assert lenses[0]["name"] == "only"
