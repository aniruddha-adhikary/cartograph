from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "cartograph.flow",
        "cli": "cartograph flow --graph cartograph-out/graph.json --anchor <anchor>",
        "description": "Return a closed cross-service flow subgraph from an endpoint, path, topic, or node id.",
    },
    {
        "name": "cartograph.find_callers",
        "cli": "cartograph find-callers --graph cartograph-out/graph.json --symbol <symbol>",
        "description": "Return graph nodes and edges that call or emit to a symbol, path, or topic.",
    },
    {
        "name": "cartograph.find_callees",
        "cli": "cartograph find-callees --graph cartograph-out/graph.json --symbol <symbol>",
        "description": "Return graph nodes and edges called or consumed by a symbol, path, or topic.",
    },
    {
        "name": "cartograph.endpoints_in_service",
        "cli": "cartograph endpoints-in-service --graph cartograph-out/graph.json --service <service>",
        "description": "List Endpoint nodes in one service, optionally filtered by path.",
    },
    {
        "name": "cartograph.cross_service_edges",
        "cli": "cartograph cross-service-edges --graph cartograph-out/graph.json [--from-service <service>] [--to-service <service>]",
        "description": "List cross-service HTTP and message edges.",
    },
    {
        "name": "cartograph.kafka_topics",
        "cli": "cartograph kafka-topics --graph cartograph-out/graph.json [--consumer-service <service>]",
        "description": "Group message bus producers, consumers, and delivery edges by topic.",
    },
    {
        "name": "cartograph.coverage_report",
        "cli": "cartograph coverage-report --graph cartograph-out/graph.json",
        "description": "Return per-service source and confidence breakdowns.",
    },
    {
        "name": "cartograph.search",
        "cli": "cartograph search --graph cartograph-out/graph.json --query <query>",
        "description": "Search graph nodes by exact match, with low-confidence deterministic fallback.",
    },
    {
        "name": "cartograph.explain_flow",
        "cli": "cartograph explain --graph cartograph-out/graph.json --anchor <anchor>",
        "description": "Return a structured deterministic narrative for a flow.",
    },
    {
        "name": "cartograph.lens",
        "cli": "cartograph lens --graph cartograph-out/graph.json --name <lens> [--workspace .] [--params <json>]",
        "description": "Return a generated lens or a raw Kuzu Cypher project lens from .cartograph/lenses.",
    },
    {
        "name": "cartograph.lens_list",
        "cli": "cartograph lens list --graph cartograph-out/graph.json [--workspace .]",
        "description": "List generated and configured lenses with their return signatures.",
    },
]


def tool_catalog() -> dict[str, Any]:
    return {"tools": TOOLS}
