from __future__ import annotations

import json
from pathlib import Path

from cartograph.cli import main
from cartograph.indexer import index_workspace
from cartograph.lens_specs import load_lens_specs
from cartograph.query import (
    cgc_tool,
    coverage_report,
    cross_service_edges,
    endpoints_in_service,
    explain_flow,
    find_callees,
    find_callers,
    flow,
    kafka_topics,
    lens,
    list_lenses,
    search,
)
from cartograph.serve import dispatch
from cartograph.tools import tool_catalog
from cartograph.trace import import_trace


def citypermits_graph() -> dict:
    workspace = Path(__file__).parents[1] / "fixtures" / "citypermits-workspace"
    return index_workspace(workspace).to_dict()


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def test_flow_returns_closed_cross_service_async_subgraph() -> None:
    graph = citypermits_graph()

    result = flow(graph, "/api/permits/motor-vehicle")

    assert result["mode"] == "anchored"
    assert result["services_touched"] == ["inspections-api", "permits-api", "web"]
    assert result["stats"]["n_cross_repo_http"] == 1
    assert result["stats"]["n_kafka_deliveries"] == 3
    assert result["confidence_summary"]["high"] >= 1
    assert result["graph_version"]


def test_m2_tools_answer_reference_questions() -> None:
    graph = citypermits_graph()

    outbound = cross_service_edges(graph, {"from_service": "web"})
    topics = kafka_topics(graph, {"consumer_service": "inspections-api"})
    endpoints = endpoints_in_service(graph, "permits-api", "/api/permits")
    callers = find_callers(graph, "permit.approved")
    callees = find_callees(graph, "/api/permits/motor-vehicle")

    assert outbound["stats"]["n_cross_repo_http"] == 5
    assert "permit.approved" in topics["topics"]
    assert topics["topics"]["permit.approved"]["producers"] == ["permits-api"]
    assert len(endpoints["nodes"]) == 5
    assert any(edge["type"] == "KAFKA_DELIVERS" for edge in callers["edges"])
    assert callees["stats"]["n_edges"] >= 0


def test_search_coverage_explain_and_lenses_are_structured() -> None:
    graph = citypermits_graph()

    exact = search(graph, "motor-vehicle")
    fallback = search(graph, "automobile license", fallback=True)
    coverage = coverage_report(graph)
    explanation = explain_flow(graph, "/api/permits/motor-vehicle")
    endpoints_lens = lens(graph, "pattern.endpoints")
    route_lens = lens(graph, "route.api.permits")
    domain_lens = lens(graph, "domain.permits")

    assert exact["fallback_used"] is False
    assert fallback["fallback_used"] is True
    assert fallback["confidence_summary"]["low"] >= 1
    assert "permits-api" in coverage["services"]
    assert explanation["steps"]
    assert len(endpoints_lens["nodes"]) >= 5
    assert len([node for node in route_lens["nodes"] if node["label"] == "Endpoint"]) == 5
    assert domain_lens["mode"] == "domain"
    assert domain_lens["persisted"] is True
    assert len(domain_lens["nodes"]) >= 2


def test_configured_lenses_are_raw_kuzu_cypher_queries(capsys, tmp_path: Path) -> None:
    graph = citypermits_graph()
    graph_path = write_json(tmp_path / "graph.json", graph)
    lenses_dir = tmp_path / "layer" / "lenses"
    write_json(
        lenses_dir / "project.json",
        {
            "project.motor-vehicle-cross-tier": {
                "kind": "query",
                "language": "kuzu-cypher",
                "returns": {
                    "caller": "HttpCall",
                    "call": "CROSSES_TIER",
                    "target": "Endpoint",
                },
                "query": [
                    "MATCH (caller:HttpCall)-[call:CROSSES_TIER]->(target:Endpoint)",
                    "WHERE target.path CONTAINS $path",
                    "RETURN caller, call, target",
                ],
            },
        },
    )

    specs = load_lens_specs(lenses_dir=lenses_dir)
    result = lens(graph, "project.motor-vehicle-cross-tier", specs, params={"path": "motor-vehicle"})

    assert result["configured"] is True
    assert result["mode"] == "kuzu-query"
    assert result["returns"]["target"] == "Endpoint"
    assert result["rows"]
    assert any(node.get("path") == "/api/permits/motor-vehicle" for node in result["nodes"])
    assert any(edge["type"] == "CROSSES_TIER" for edge in result["edges"])

    assert (
        main(
            [
                "lens",
                "--graph",
                str(graph_path),
                "--name",
                "project.motor-vehicle-cross-tier",
                "--lenses-dir",
                str(lenses_dir),
                "--params",
                '{"path":"motor-vehicle"}',
            ]
        )
        == 0
    )
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["mode"] == "kuzu-query"
    assert cli_result["stats"]["n_edges"] >= 1

    assert main(["lens", "list", "--graph", str(graph_path), "--lenses-dir", str(lenses_dir)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert any(item["name"] == "project.motor-vehicle-cross-tier" for item in listed["lenses"])
    assert any(item["name"] == "domain.permits" for item in list_lenses(graph, specs)["lenses"])


def test_kuzu_query_lens_can_query_persisted_lens_members(tmp_path: Path) -> None:
    graph = citypermits_graph()
    lenses_dir = tmp_path / "layer" / "lenses"
    write_json(
        lenses_dir / "project.json",
        {
            "project.permits-domain-raw": {
                "kind": "query",
                "returns": {
                    "lens": "Lens",
                    "contains": "CONTAINS",
                    "member": "Endpoint",
                },
                "query": [
                    "MATCH (lens:Lens)-[contains:CONTAINS]->(member:Endpoint)",
                    "WHERE lens.name = 'domain.permits'",
                    "RETURN lens, contains, member",
                ],
            }
        },
    )

    result = lens(graph, "project.permits-domain-raw", load_lens_specs(lenses_dir=lenses_dir))

    assert result["mode"] == "kuzu-query"
    assert result["configured"] is True
    assert any(node.get("label") == "Lens" and node.get("name") == "domain.permits" for node in result["nodes"])
    assert any(node.get("label") == "Endpoint" and "permits" in node.get("path", "") for node in result["nodes"])


def test_trace_import_adds_stub_for_runtime_only_target(tmp_path: Path) -> None:
    graph = citypermits_graph()
    trace_path = write_json(
        tmp_path / "trace.json",
        {
            "spans": [
                {
                    "name": "POST /api/runtime-only",
                    "service": "web",
                    "attributes": {
                        "peer.service": "runtime-api",
                        "http.route": "/api/runtime-only",
                    },
                }
            ]
        },
    )

    merged = import_trace(graph, trace_path)
    merged_again = import_trace(merged, trace_path)

    assert len(merged["nodes"]) == len(graph["nodes"]) + 1
    assert any(node["service"] == "runtime-api" and node["confidence"] == "low" for node in merged["nodes"])
    assert any(edge.get("source") == "otel-trace" for edge in merged["edges"])
    assert len(merged_again["nodes"]) == len(merged["nodes"])
    assert len(merged_again["edges"]) == len(merged["edges"])


def test_trace_import_supports_real_otlp_resource_spans(tmp_path: Path) -> None:
    graph = citypermits_graph()
    trace_path = write_json(
        tmp_path / "otlp.json",
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "web"}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "POST /api/resource-only",
                                    "attributes": [
                                        {"key": "peer.service", "value": {"stringValue": "resource-api"}},
                                        {"key": "http.route", "value": {"stringValue": "/api/resource-only"}},
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )

    merged = import_trace(graph, trace_path)

    assert any(node["id"].startswith("resource-api:otel:") for node in merged["nodes"])
    assert merged["meta"]["trace_import"]["spans"] == 1


def test_cgc_adapter_and_cli_surface(capsys, tmp_path: Path) -> None:
    graph = citypermits_graph()
    graph_path = write_json(tmp_path / "graph.json", graph)

    definition = cgc_tool(graph, "cgc.get_symbol_definition", {"symbol": "motor-vehicle"})
    unsupported = cgc_tool(graph, "cgc.get_class_hierarchy", {"class": "PermitController"})

    assert definition["label"] == "Endpoint"
    assert unsupported["error"] == "not_supported"

    assert main(["kafka-topics", "--graph", str(graph_path), "--consumer-service", "inspections-api"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "permit.approved" in result["topics"]


def test_search_ranking_prefers_semantic_synonyms_for_legacy_terms() -> None:
    graph = citypermits_graph()

    result = search(graph, "automobile license", fallback=True, limit=3)

    assert result["nodes"][0]["path"] == "/api/permits/motor-vehicle"
    assert "path" in result["nodes"][0]["match_reasons"]
    assert result["nodes"][0]["source"] == "deterministic-search"


def test_server_dispatch_supports_mcp_style_tool_calls() -> None:
    graph = citypermits_graph()

    result = dispatch(graph, {}, {}, "cartograph.endpoints_in_service", {"service": "permits-api"})

    assert result["name"] == "endpoints:permits-api"
    assert len(result["nodes"]) == 5


def test_tools_command_exposes_cli_first_catalog(capsys) -> None:
    assert main(["tools"]) == 0

    catalog = json.loads(capsys.readouterr().out)
    names = {tool["name"] for tool in catalog["tools"]}

    assert "cartograph.flow" in names
    assert "cartograph.search" in names
    assert all("cli" in tool and tool["cli"].startswith("cartograph ") for tool in catalog["tools"])
    assert tool_catalog() == catalog
