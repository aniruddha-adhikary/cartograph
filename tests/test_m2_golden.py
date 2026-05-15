from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cartograph.indexer import index_workspace
from cartograph.query import (
    coverage_report,
    cross_service_edges,
    endpoints_in_service,
    explain_flow,
    flow,
    kafka_topics,
    lens,
    search,
)

ROOT = Path(__file__).parents[1]


def graph() -> dict[str, Any]:
    return index_workspace(ROOT / "fixtures" / "citypermits-workspace").to_dict()


def load_golden(path: str) -> Any:
    return json.loads((ROOT / "fixtures" / "golden" / path).read_text(encoding="utf-8"))


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "<workspace>" if key == "workspace" else normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), "<repo>")
    return value


def assert_golden(path: str, value: Any) -> None:
    assert normalize(value) == load_golden(path)


def test_citypermits_graph_matches_golden_snapshot() -> None:
    assert_golden("citypermits.graph.json", graph())


def test_m2_reference_commands_match_golden_snapshots() -> None:
    data = graph()
    cases = {
        "m2/flow-motorvehicle.json": flow(data, "/api/permits/motor-vehicle"),
        "m2/cross-service-web.json": cross_service_edges(data, {"from_service": "web"}),
        "m2/kafka-topics-inspections.json": kafka_topics(data, {"consumer_service": "inspections-api"}),
        "m2/endpoints-permits.json": endpoints_in_service(data, "permits-api", "/api/permits"),
        "m2/coverage-report.json": coverage_report(data),
        "m2/search-automobile-license.json": search(data, "automobile license", fallback=True, limit=3),
        "m2/explain-motorvehicle.json": explain_flow(data, "/api/permits/motor-vehicle"),
        "m2/lens-domain-permits.json": lens(data, "domain.permits"),
    }
    for path, value in cases.items():
        assert_golden(path, value)
