from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "golden"
sys.path.insert(0, str(ROOT))

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


def main() -> int:
    graph = index_workspace(ROOT / "fixtures" / "citypermits-workspace").to_dict()
    write(OUT / "citypermits.graph.json", normalize(graph))
    cases = {
        "flow-motorvehicle.json": flow(graph, "/api/permits/motor-vehicle"),
        "cross-service-web.json": cross_service_edges(graph, {"from_service": "web"}),
        "kafka-topics-inspections.json": kafka_topics(graph, {"consumer_service": "inspections-api"}),
        "endpoints-permits.json": endpoints_in_service(graph, "permits-api", "/api/permits"),
        "coverage-report.json": coverage_report(graph),
        "search-automobile-license.json": search(graph, "automobile license", fallback=True, limit=3),
        "explain-motorvehicle.json": explain_flow(graph, "/api/permits/motor-vehicle"),
        "lens-domain-permits.json": lens(graph, "domain.permits"),
    }
    for name, value in cases.items():
        write(OUT / "m2" / name, normalize(value))
    return 0


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if key == "workspace":
                output[key] = "<workspace>"
            else:
                output[key] = normalize(item)
        return output
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), "<repo>")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    raise SystemExit(main())
