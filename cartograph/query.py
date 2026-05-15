from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from .lens_specs import run_lens_spec

FLOW_EDGE_TYPES = {
    "HANDLES",
    "HANDLES_KAFKA",
    "HANDLES_MESSAGE",
    "CROSSES_TIER",
    "KAFKA_DELIVERS",
    "MESSAGE_DELIVERS",
    "EMITS",
}


def load_graph(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def graph_version(graph: dict[str, Any]) -> str:
    node_ids = sorted(str(node.get("id", "")) for node in graph.get("nodes", []))
    edge_keys = sorted(f"{edge.get('type')}:{edge.get('from')}:{edge.get('to')}" for edge in graph.get("edges", []))
    digest = hashlib.sha256("\n".join([*node_ids, *edge_keys]).encode("utf-8")).hexdigest()
    return digest[:16]


def confidence_summary(nodes: list[dict[str, Any]], edges: list[dict[str, Any]] | None = None) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for item in [*nodes, *(edges or [])]:
        confidence = item.get("confidence")
        if confidence in counts:
            counts[confidence] += 1
    return counts


def edge_stats(edges: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "n_edges": len(edges),
        "n_cross_repo_http": sum(1 for edge in edges if edge.get("type") == "CROSSES_TIER"),
        "n_kafka_deliveries": sum(1 for edge in edges if edge.get("type") == "KAFKA_DELIVERS"),
        "n_message_deliveries": sum(1 for edge in edges if str(edge.get("type", "")).endswith("DELIVERS")),
    }


def graph_response(
    name: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], graph: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    services = sorted({str(node["service"]) for node in nodes if node.get("service")})
    stats = {
        "n_nodes": len(nodes),
        "n_services": len(services),
        **edge_stats(edges),
    }
    return {
        "name": name,
        "nodes": sorted_nodes(nodes),
        "edges": sorted_edges(edges),
        "services_touched": services,
        "confidence_summary": confidence_summary(nodes, edges),
        "graph_version": graph_version(graph),
        "stats": stats,
        **extra,
    }


def flow(graph: dict[str, Any], anchor: str, depth: int = 8) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_id = {node["id"]: node for node in nodes}
    starts = match_nodes(nodes, anchor)
    if not starts:
        return graph_response(f"flow:{anchor}", [], [], graph, anchor=anchor, mode="anchored", anchors=[])

    visited: set[str] = {node["id"] for node in starts}
    selected_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    outgoing = adjacency(edges, "from")
    incoming = adjacency(edges, "to")

    for start in starts:
        for edge in incoming.get(start["id"], []):
            if edge.get("type") == "CROSSES_TIER":
                selected_edges[edge_key(edge)] = edge
                visited.add(edge["from"])

    queue = deque((node_id, 0) for node_id in sorted(visited))
    while queue:
        node_id, distance = queue.popleft()
        if distance >= depth:
            continue
        for edge in outgoing.get(node_id, []):
            if edge.get("type") not in FLOW_EDGE_TYPES:
                continue
            selected_edges[edge_key(edge)] = edge
            target = edge["to"]
            if target not in visited:
                visited.add(target)
                queue.append((target, distance + 1))

        node = by_id.get(node_id, {})
        if (
            node.get("label") in {"Endpoint", "KafkaConsumer", "MessageConsumer"}
            or node.get("message_role") == "consumer"
        ):
            for producer in same_service_producers(nodes, node.get("service")):
                if producer["id"] not in visited:
                    visited.add(producer["id"])
                    queue.append((producer["id"], distance + 1))

    result_nodes = [by_id[node_id] for node_id in visited if node_id in by_id]
    result_edges = list(selected_edges.values())
    return graph_response(
        f"flow:{anchor}",
        result_nodes,
        result_edges,
        graph,
        anchor=anchor,
        mode="anchored",
        anchors=[node["id"] for node in starts],
    )


def find_callers(graph: dict[str, Any], symbol: str) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    matched = match_nodes(nodes, symbol)
    matched_ids = {node["id"] for node in matched}
    selected_edges = [edge for edge in edges if edge.get("to") in matched_ids]
    selected_ids = {edge["from"] for edge in selected_edges} | matched_ids
    if not selected_edges:
        selected_edges = [edge for edge in edges if edge_matches_symbol(edge, nodes, symbol, incoming=True)]
        selected_ids = {edge["from"] for edge in selected_edges} | {edge["to"] for edge in selected_edges}
    return graph_response(f"callers:{symbol}", nodes_by_id(nodes, selected_ids), selected_edges, graph, symbol=symbol)


def find_callees(graph: dict[str, Any], symbol: str) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    matched = match_nodes(nodes, symbol)
    matched_ids = {node["id"] for node in matched}
    selected_edges = [edge for edge in edges if edge.get("from") in matched_ids]
    selected_ids = {edge["to"] for edge in selected_edges} | matched_ids
    if not selected_edges:
        selected_edges = [edge for edge in edges if edge_matches_symbol(edge, nodes, symbol, incoming=False)]
        selected_ids = {edge["from"] for edge in selected_edges} | {edge["to"] for edge in selected_edges}
    return graph_response(f"callees:{symbol}", nodes_by_id(nodes, selected_ids), selected_edges, graph, symbol=symbol)


def endpoints_in_service(graph: dict[str, Any], service: str, path: str | None = None) -> dict[str, Any]:
    endpoints = [
        node
        for node in graph.get("nodes", [])
        if node.get("label") == "Endpoint"
        and node.get("service") == service
        and (path is None or path in str(node.get("path", "")))
    ]
    return graph_response(f"endpoints:{service}", endpoints, [], graph, service=service, path=path)


def cross_service_edges(graph: dict[str, Any], filter: dict[str, Any] | None = None) -> dict[str, Any]:
    filter = filter or {}
    wanted = {"CROSSES_TIER", "KAFKA_DELIVERS", "MESSAGE_DELIVERS"}
    edges = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("type") in wanted
        and edge.get("cross_repo", edge.get("from_service") != edge.get("to_service"))
        and matches_filter(edge, filter)
    ]
    ids = {edge["from"] for edge in edges} | {edge["to"] for edge in edges}
    return graph_response("cross-service-edges", nodes_by_id(graph.get("nodes", []), ids), edges, graph, filter=filter)


def kafka_topics(graph: dict[str, Any], filter: dict[str, Any] | None = None) -> dict[str, Any]:
    filter = filter or {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_id = {node["id"]: node for node in nodes}
    topics: dict[str, dict[str, Any]] = {}

    for node in nodes:
        if node.get("message_role") == "producer":
            topic = str(node.get("topic", ""))
            bucket = topics.setdefault(topic, topic_bucket(topic, node.get("bus", "kafka")))
            bucket["producers"].append(node.get("service"))
        if node.get("message_role") == "consumer":
            for topic in node.get("topics", []):
                bucket = topics.setdefault(str(topic), topic_bucket(str(topic), node.get("bus", "kafka")))
                bucket["consumers"].append(node.get("service"))

    delivery_edges = [edge for edge in edges if str(edge.get("type", "")).endswith("DELIVERS")]
    for edge in delivery_edges:
        producer = by_id.get(edge["from"], {})
        consumer = by_id.get(edge["to"], {})
        topic = str(producer.get("topic") or first(consumer.get("topics", [])) or "")
        bucket = topics.setdefault(topic, topic_bucket(topic, producer.get("bus", consumer.get("bus", "kafka"))))
        bucket["links"].append(
            {
                "from_service": edge.get("from_service"),
                "to_service": edge.get("to_service"),
                "confidence": edge.get("confidence"),
                "edge_type": edge.get("type"),
            }
        )

    filtered = {
        topic: normalize_topic_bucket(bucket)
        for topic, bucket in topics.items()
        if topic and topic_matches(bucket, filter)
    }
    return {
        "name": "kafka-topics",
        "topics": dict(sorted(filtered.items())),
        "confidence_summary": confidence_summary(
            [node for node in nodes if node.get("message_role") in {"producer", "consumer"}], delivery_edges
        ),
        "graph_version": graph_version(graph),
        "stats": {"n_topics": len(filtered), "n_delivery_edges": len(delivery_edges)},
        "filter": filter,
    }


def coverage_report(graph: dict[str, Any], threshold: float = 0.8) -> dict[str, Any]:
    services: dict[str, dict[str, Any]] = {}
    for node in graph.get("nodes", []):
        service = node.get("service", "unknown")
        item = services.setdefault(service, {"total_nodes": 0, "sources": Counter(), "confidence": Counter()})
        item["total_nodes"] += 1
        item["sources"][source_family(str(node.get("source", "")))] += 1
        item["confidence"][node.get("confidence", "unknown")] += 1

    service_reports = {}
    below_threshold = []
    for service, item in sorted(services.items()):
        total = item["total_nodes"] or 1
        pack_nodes = item["sources"].get("pack", 0)
        llm_nodes = item["sources"].get("llm", 0)
        coverage_ratio = pack_nodes / total
        report = {
            "total_nodes": item["total_nodes"],
            "source_breakdown": dict(sorted(item["sources"].items())),
            "confidence_breakdown": dict(sorted(item["confidence"].items())),
            "pack_coverage_ratio": round(coverage_ratio, 4),
            "llm_ratio": round(llm_nodes / total, 4),
        }
        service_reports[service] = report
        if coverage_ratio < threshold:
            below_threshold.append(service)

    return {
        "name": "coverage-report",
        "services": service_reports,
        "below_threshold": below_threshold,
        "threshold": threshold,
        "graph_version": graph_version(graph),
    }


def search(
    graph: dict[str, Any], query: str, fallback: bool = True, limit: int = 10, label: str | None = None
) -> dict[str, Any]:
    nodes = [node for node in graph.get("nodes", []) if label is None or node.get("label") == label]
    exact = rank_search_candidates(nodes, query, limit, exact_only=True)
    if exact:
        exact_nodes = [item[0] for item in exact]
        response = graph_response(
            f"search:{query}",
            exact_nodes,
            incident_edges(graph.get("edges", []), {node["id"] for node in exact_nodes}),
            graph,
            query=query,
            fallback_used=False,
        )
        response["nodes"] = exact_nodes
        return response
    if not fallback:
        return graph_response(f"search:{query}", [], [], graph, query=query, fallback_used=False)

    ranked = rank_search_candidates(nodes, query, limit)
    fallback_nodes = [
        {
            **node,
            "confidence": "low",
            "source": "deterministic-search",
            "similarity": score,
            "match_reasons": reasons,
        }
        for node, score, reasons in ranked
    ]
    response = graph_response(f"search:{query}", fallback_nodes, [], graph, query=query, fallback_used=True)
    response["nodes"] = fallback_nodes
    return response


def explain_flow(graph: dict[str, Any], anchor: str, depth: int = 8) -> dict[str, Any]:
    result = flow(graph, anchor, depth)
    by_id = {node["id"]: node for node in result["nodes"]}
    steps = []
    async_chains = []
    for hop, edge in enumerate(ordered_flow_edges(result), 1):
        src = by_id.get(edge["from"], {})
        dst = by_id.get(edge["to"], {})
        detail = src.get("topic") or src.get("path") or dst.get("path") or ", ".join(dst.get("topics", [])) or ""
        description = edge_display(edge, src, dst)
        if detail:
            description += f" ({detail})"
        steps.append(
            {"hop": hop, "service": edge.get("from_service"), "node": node_display(src), "description": description}
        )
        if str(edge.get("type", "")).endswith("DELIVERS"):
            async_chains.append(description)
    confidence_notes = [
        f"{count} {tier}-confidence item(s)"
        for tier, count in result["confidence_summary"].items()
        if count and tier != "high"
    ]
    entrypoints = [node_display(node) for node in result["nodes"] if node.get("id") in result.get("anchors", [])]
    return {
        "anchor": anchor,
        "summary": f"Flow touches {result['stats']['n_services']} service(s): {', '.join(result['services_touched'])}.",
        "entrypoints": entrypoints,
        "services_touched": result["services_touched"],
        "steps": steps,
        "ordered_steps": steps,
        "async_loops": async_chains,
        "async_chains": async_chains,
        "confidence_notes": confidence_notes,
        "recommended_next_commands": [
            f"cartograph flow --graph <graph> --anchor {json.dumps(anchor)}",
            "cartograph cross-service-edges --graph <graph>",
            "cartograph search --graph <graph> --query <term>",
        ],
        "flow": result,
    }


def ordered_flow_edges(flow_result: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        flow_result.get("edges", []),
        key=lambda edge: (
            0 if edge.get("type") == "CROSSES_TIER" else 1 if str(edge.get("type", "")).endswith("DELIVERS") else 2,
            str(edge.get("from_service")),
            str(edge.get("to_service")),
            str(edge.get("from")),
        ),
    )


def node_display(node: dict[str, Any]) -> str:
    if node.get("label") == "Endpoint":
        return f"{node.get('http_method', 'GET')} {node.get('path')}"
    if node.get("topic"):
        return f"{node.get('label')}({node.get('topic')})"
    if node.get("topics"):
        return f"{node.get('label')}({', '.join(node.get('topics', []))})"
    return str(node.get("handler") or node.get("name") or node.get("id", ""))


def edge_display(edge: dict[str, Any], src: dict[str, Any], dst: dict[str, Any]) -> str:
    if edge.get("type") == "CROSSES_TIER":
        return f"{edge.get('from_service')} calls {edge.get('to_service')} {node_display(dst)}"
    if str(edge.get("type", "")).endswith("DELIVERS"):
        return f"{edge.get('from_service')} publishes to {edge.get('to_service')} {node_display(dst)}"
    return f"{edge.get('from_service')} reaches {edge.get('to_service')} via {edge.get('type')}"


def explain(graph: dict[str, Any], anchor: str) -> str:
    result = explain_flow(graph, anchor)
    lines = [result["summary"]]
    for step in result["steps"]:
        lines.append(f"- {step['description']}")
    for note in result["confidence_notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def lens(
    graph: dict[str, Any],
    name: str,
    lens_specs: dict[str, Any] | None = None,
    _seen: set[str] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lens_specs = lens_specs or {}
    _seen = _seen or set()
    if name in _seen:
        raise ValueError(f"cyclic lens reference: {' -> '.join([*_seen, name])}")
    if name in lens_specs:
        result = run_lens_spec(
            graph,
            name,
            lens_specs[name],
            lambda child: lens(graph, child, lens_specs, {*_seen, name}),
            params,
        )
        return graph_response(
            name,
            result["nodes"],
            result["edges"],
            graph,
            mode=result["mode"],
            anchors=result["anchors"],
            configured=True,
            rows=result.get("rows", []),
            query=result.get("query"),
            returns=result.get("returns", {}),
        )
    persisted = persisted_lens(graph, name)
    if persisted:
        return persisted
    if name == "pattern.endpoints":
        nodes = [node for node in graph.get("nodes", []) if node.get("label") == "Endpoint"]
        return graph_response(name, nodes, [], graph, mode="pattern", anchors=[name])
    if name == "pattern.controllers":
        nodes = [
            node
            for node in graph.get("nodes", [])
            if node.get("label") == "Service" and "controller" in str(node.get("kind", ""))
        ]
        return graph_response(name, nodes, [], graph, mode="pattern", anchors=[name])
    if name == "pattern.cross_tier_calls":
        edges = [edge for edge in graph.get("edges", []) if edge.get("type") == "CROSSES_TIER"]
        ids = {edge["from"] for edge in edges} | {edge["to"] for edge in edges}
        return graph_response(
            name, nodes_by_id(graph.get("nodes", []), ids), edges, graph, mode="pattern", anchors=[name]
        )
    if name in {"pattern.kafka_bus", "pattern.message_bus"}:
        nodes = [node for node in graph.get("nodes", []) if node.get("message_role") in {"producer", "consumer"}]
        ids = {node["id"] for node in nodes}
        edges = [edge for edge in graph.get("edges", []) if str(edge.get("type", "")).endswith("DELIVERS")]
        ids |= {edge["from"] for edge in edges} | {edge["to"] for edge in edges}
        return graph_response(
            name, nodes_by_id(graph.get("nodes", []), ids), edges, graph, mode="pattern", anchors=[name]
        )
    if name == "pattern.components":
        nodes = [node for node in graph.get("nodes", []) if node.get("label") == "Component"]
        return graph_response(name, nodes, [], graph, mode="pattern", anchors=[name])
    if name.startswith("route."):
        prefix = "/" + name.split(".", 1)[1].replace(".", "/").strip("/")
        nodes = [
            node
            for node in graph.get("nodes", [])
            if node.get("label") == "Endpoint" and str(node.get("path", "")).startswith(prefix)
        ]
        ids = {node["id"] for node in nodes}
        edges = [edge for edge in graph.get("edges", []) if edge.get("to") in ids or edge.get("from") in ids]
        ids |= {edge["from"] for edge in edges} | {edge["to"] for edge in edges}
        return graph_response(
            name, nodes_by_id(graph.get("nodes", []), ids), edges, graph, mode="route-pattern", anchors=[prefix]
        )
    generated = route_pattern_lenses(graph).get(name)
    if generated:
        return generated
    generated = domain_lenses(graph).get(name)
    if generated:
        return generated
    raise ValueError(f"unknown lens {name}")


def list_lenses(graph: dict[str, Any], lens_specs: dict[str, Any] | None = None) -> dict[str, Any]:
    configured = [
        {
            "name": name,
            "kind": spec.get("kind"),
            "language": spec.get("language", "kuzu-cypher"),
            "returns": spec.get("returns", {}),
            "params": spec.get("params", {}),
            "source": "configured",
        }
        for name, spec in sorted((lens_specs or {}).items())
    ]
    persisted = [
        {
            "name": node.get("name"),
            "kind": "persisted",
            "mode": node.get("mode"),
            "returns": {"member": "Node"},
            "params": {},
            "source": "graph",
        }
        for node in sorted_nodes(graph.get("nodes", []))
        if node.get("label") == "Lens" and node.get("name")
    ]
    builtin: list[dict[str, Any]] = [
        {"name": name, "kind": "builtin", "returns": {"member": "Node"}, "params": {}, "source": "cartograph"}
        for name in [
            "pattern.endpoints",
            "pattern.controllers",
            "pattern.cross_tier_calls",
            "pattern.kafka_bus",
            "pattern.message_bus",
            "pattern.components",
        ]
    ]
    dynamic = [
        {"name": name, "kind": "dynamic", "returns": {"member": "Node"}, "params": {}, "source": "cartograph"}
        for name in [*route_pattern_lenses(graph), *domain_lenses(graph)]
    ]
    by_name = {str(item["name"]): item for item in [*builtin, *persisted, *configured, *dynamic]}
    return {"lenses": [by_name[name] for name in sorted(by_name)], "stats": {"n_lenses": len(by_name)}}


def persisted_lens(graph: dict[str, Any], name: str) -> dict[str, Any] | None:
    lens_nodes = [node for node in graph.get("nodes", []) if node.get("label") == "Lens" and node.get("name") == name]
    if not lens_nodes:
        return None
    lens_node = sorted_nodes(lens_nodes)[0]
    member_ids = {
        edge["to"]
        for edge in graph.get("edges", [])
        if edge.get("type") == "CONTAINS" and edge.get("from") == lens_node["id"]
    }
    member_nodes = nodes_by_id(graph.get("nodes", []), member_ids)
    member_edges = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("from") in member_ids and edge.get("to") in member_ids and edge.get("type") != "CONTAINS"
    ]
    return graph_response(
        name,
        member_nodes,
        member_edges,
        graph,
        mode=lens_node.get("mode", "persisted"),
        anchors=lens_node.get("anchors", [name]),
        persisted=True,
        lens_id=lens_node["id"],
    )


def route_pattern_lenses(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in graph.get("nodes", []):
        if node.get("label") != "Endpoint":
            continue
        path = str(node.get("path", "/"))
        parts = [part for part in path.split("/") if part and not part.startswith("{")]
        if len(parts) >= 2 and parts[0] == "api":
            key = f"route.api.{parts[1]}"
        elif parts:
            key = f"route.{parts[0]}"
        else:
            key = "route.root"
        groups[key].append(node)
    return {
        name: graph_response(
            name,
            nodes,
            [],
            graph,
            mode="route-pattern",
            anchors=[min((node.get("path", "") for node in nodes), key=len)],
        )
        for name, nodes in groups.items()
    }


def domain_lenses(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, set[str]] = defaultdict(set)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        if node.get("label") not in {"Endpoint", "Component"} and node.get("message_role") not in {
            "producer",
            "consumer",
        }:
            continue
        for token in domain_tokens(node):
            groups[token].add(node["id"])

    for edge in edges:
        if edge.get("type") != "CROSSES_TIER":
            continue
        source = by_id.get(edge["from"], {})
        target = by_id.get(edge["to"], {})
        shared = set(domain_tokens(source)) | set(domain_tokens(target))
        for token in shared:
            if token in groups:
                groups[token].update({edge["from"], edge["to"]})

    lenses = {}
    for token, ids in groups.items():
        if len(ids) < 2:
            continue
        selected_edges = [edge for edge in edges if edge.get("from") in ids and edge.get("to") in ids]
        lenses[f"domain.{token}"] = graph_response(
            f"domain.{token}",
            nodes_by_id(nodes, ids),
            selected_edges,
            graph,
            mode="domain",
            anchors=[token],
        )
    return lenses


def domain_tokens(node: dict[str, Any]) -> list[str]:
    ignored = {
        "api",
        "src",
        "main",
        "java",
        "example",
        "controller",
        "resource",
        "service",
        "listener",
        "kafka",
        "http",
        "get",
        "post",
        "put",
        "delete",
        "patch",
    }
    values = [
        str(node.get("path", "")),
        str(node.get("handler", "")),
        str(node.get("topic", "")),
        " ".join(str(topic) for topic in node.get("topics", [])),
        str(node.get("name", "")),
    ]
    output = []
    for token in tokens(" ".join(values)):
        if len(token) > 2 and token not in ignored and not token.isdigit():
            output.append(token)
    return sorted(set(output))


def cgc_tool(graph: dict[str, Any], tool: str, params: dict[str, Any] | None = None) -> Any:
    params = params or {}
    if tool == "cgc.get_symbol_definition":
        result = search(graph, str(params.get("symbol", "")), fallback=False, limit=1)
        return result["nodes"][0] if result["nodes"] else None
    if tool == "cgc.find_references":
        return find_callers(graph, str(params.get("symbol", "")))
    if tool == "cgc.get_callees":
        return find_callees(graph, str(params.get("symbol", "")))
    if tool == "cgc.get_file_symbols":
        file_path = str(params.get("file_path", ""))
        nodes = [
            node for node in graph.get("nodes", []) if node.get("file") == file_path or node.get("path") == file_path
        ]
        return graph_response(tool, nodes, [], graph, file_path=file_path)
    if tool == "cgc.get_dependencies":
        return flow(graph, str(params.get("symbol", "")), depth=2)
    return {
        "error": "not_supported",
        "cartograph_equivalent": "cartograph.search(query) or cartograph.flow(anchor)",
        "reason": "Cartograph M2 is framework-endpoint-centric and does not expose this CGC symbol operation.",
    }


def match_nodes(nodes: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    lowered = query.lower()
    return [node for node in nodes if lowered in searchable_text(node).lower()]


def searchable_text(node: dict[str, Any]) -> str:
    values = []
    for value in node.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value)
    return " ".join(values)


def semantic_candidates(nodes: list[dict[str, Any]], query: str, limit: int) -> list[tuple[dict[str, Any], float]]:
    return [(node, score) for node, score, _ in rank_search_candidates(nodes, query, limit)]


def rank_search_candidates(
    nodes: list[dict[str, Any]], query: str, limit: int, exact_only: bool = False
) -> list[tuple[dict[str, Any], float, list[str]]]:
    phrase = query.lower()
    query_tokens = ["exact-only"] if exact_only else expand_query_tokens(tokens(query))
    ranked: list[tuple[dict[str, Any], float, list[str]]] = []
    for node in nodes:
        score, reasons = search_score(node, query_tokens, phrase)
        if exact_only and "exact" not in reasons:
            continue
        if score:
            ranked.append((node, round(score, 4), reasons))
    if ranked:
        return sorted(ranked, key=lambda item: (-item[1], item[0].get("id", "")))[:limit]
    if exact_only:
        return []
    return [(node, 0.0, ["fallback"]) for node in sorted_nodes(nodes)[:limit]]


_LABEL_PRIORITY = {"Endpoint": 0.5, "HttpCall": 0.3, "Component": 0.2, "Service": 0.1}


def search_score(node: dict[str, Any], query_tokens: list[str], query_phrase: str) -> tuple[float, list[str]]:
    weighted_fields = search_fields(node)
    reasons: list[str] = []
    score = 0.0
    for field, weight, text in weighted_fields:
        lowered = text.lower()
        field_tokens = Counter(tokens(text))
        if query_phrase and query_phrase in lowered:
            score += 10 * weight
            reasons.append("exact")
        if "exact-only" in query_tokens:
            continue
        overlap = sum(field_tokens.get(token, 0) for token in query_tokens)
        if overlap:
            score += overlap * weight
            reasons.append(field)
    if score > 0:
        score += _LABEL_PRIORITY.get(node.get("label", ""), 0)
    return score, sorted(set(reasons))


def search_fields(node: dict[str, Any]) -> list[tuple[str, float, str]]:
    topics = " ".join(str(topic) for topic in node.get("topics", []))
    return [
        ("path", 5.0, str(node.get("path", ""))),
        ("topic", 5.0, " ".join([str(node.get("topic", "")), topics])),
        ("handler", 4.0, str(node.get("handler", ""))),
        ("name", 3.0, str(node.get("name", ""))),
        ("service", 2.0, str(node.get("service", ""))),
        ("label", 1.5, str(node.get("label", ""))),
        ("file", 1.0, str(node.get("file", ""))),
        ("id", 1.0, str(node.get("id", ""))),
    ]


def expand_query_tokens(query_tokens: list[str]) -> list[str]:
    synonyms = {
        "automobile": ["motor", "vehicle"],
        "car": ["motor", "vehicle"],
        "license": ["permit"],
        "licence": ["permit"],
        "queue": ["topic"],
        "event": ["topic"],
    }
    expanded = list(query_tokens)
    for token in query_tokens:
        expanded.extend(synonyms.get(token, []))
    return expanded


def tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)]


def cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def adjacency(edges: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        output[edge[key]].append(edge)
    return output


def same_service_producers(nodes: list[dict[str, Any]], service: str | None) -> list[dict[str, Any]]:
    return [
        node for node in nodes if service and node.get("service") == service and node.get("message_role") == "producer"
    ]


def nodes_by_id(nodes: list[dict[str, Any]], ids: set[str]) -> list[dict[str, Any]]:
    return [node for node in nodes if node.get("id") in ids]


def incident_edges(edges: list[dict[str, Any]], ids: set[str]) -> list[dict[str, Any]]:
    return [edge for edge in edges if edge.get("from") in ids or edge.get("to") in ids]


def edge_matches_symbol(edge: dict[str, Any], nodes: list[dict[str, Any]], symbol: str, incoming: bool) -> bool:
    by_id = {node["id"]: node for node in nodes}
    node = by_id.get(edge["to" if incoming else "from"], {})
    return symbol.lower() in searchable_text(node).lower()


def matches_filter(item: dict[str, Any], filter: dict[str, Any]) -> bool:
    return all(value is None or item.get(key) == value for key, value in filter.items())


def topic_bucket(topic: str, bus: str) -> dict[str, Any]:
    return {"topic": topic, "bus": bus, "producers": [], "consumers": [], "links": []}


def topic_matches(bucket: dict[str, Any], filter: dict[str, Any]) -> bool:
    if filter.get("producer_service") and filter["producer_service"] not in bucket["producers"]:
        return False
    if filter.get("consumer_service") and filter["consumer_service"] not in bucket["consumers"]:
        return False
    if filter.get("bus") and filter["bus"] != bucket.get("bus"):
        return False
    return True


def normalize_topic_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        **bucket,
        "producers": sorted({service for service in bucket["producers"] if service}),
        "consumers": sorted({service for service in bucket["consumers"] if service}),
        "links": sorted(
            bucket["links"],
            key=lambda item: (str(item.get("from_service")), str(item.get("to_service")), str(item.get("edge_type"))),
        ),
    }


def source_family(source: str) -> str:
    if source.startswith("pack:"):
        return "pack"
    if source.startswith("llm:"):
        return "llm"
    if source.startswith("otel-trace"):
        return "trace"
    if source == "embedding-similarity":
        return "embedding"
    if source == "deterministic-search":
        return "search"
    if source == "cgc-import":
        return "cgc"
    return source or "unknown"


def sorted_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: str(node.get("id", "")))


def sorted_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(edges, key=lambda edge: (str(edge.get("type")), str(edge.get("from")), str(edge.get("to"))))


def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return str(edge.get("type")), str(edge.get("from")), str(edge.get("to"))


def first(values: list[Any]) -> Any:
    return values[0] if values else None
