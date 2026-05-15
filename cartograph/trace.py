from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .query import graph_version


def import_trace(graph: dict[str, Any], otlp_path: Path) -> dict[str, Any]:
    trace = json.loads(otlp_path.read_text(encoding="utf-8"))
    spans = list(iter_spans(trace))
    nodes = list(graph.get("nodes", []))
    edges = list(graph.get("edges", []))
    by_signature = node_signatures(nodes)
    added_nodes: list[dict[str, Any]] = []
    added_edges: list[dict[str, Any]] = []
    warnings: list[str] = []

    for span in spans:
        source = match_span_node(span, by_signature, role="source")
        target = match_span_node(span, by_signature, role="target")
        if not target:
            target = stub_node(span)
            if not any(node.get("id") == target["id"] for node in [*nodes, *added_nodes]):
                added_nodes.append(target)
                by_signature.update(node_signatures([target]))
        if source and target and source["id"] != target["id"]:
            edge = {
                "type": trace_edge_type(span),
                "from": source["id"],
                "to": target["id"],
                "from_service": source.get("service", span.get("service", "unknown")),
                "to_service": target.get("service", span.get("target_service", target.get("service", "unknown"))),
                "cross_repo": source.get("service") != target.get("service"),
                "confidence": "low" if target in added_nodes else "medium",
                "source": "otel-trace",
            }
            if not any(
                e.get("type") == edge["type"] and e.get("from") == edge["from"] and e.get("to") == edge["to"]
                for e in [*edges, *added_edges]
            ):
                added_edges.append(edge)
        elif not source:
            warnings.append(f"unmatched source span {span.get('name')}")

    merged = {
        **graph,
        "nodes": [*nodes, *added_nodes],
        "edges": [*edges, *added_edges],
        "meta": {
            **graph.get("meta", {}),
            "trace_import": {
                "source": str(otlp_path),
                "spans": len(spans),
                "added_nodes": len(added_nodes),
                "added_edges": len(added_edges),
                "warnings": warnings,
            },
        },
    }
    merged["meta"]["graph_version"] = graph_version(merged)
    return merged


def iter_spans(data: Any) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if "resourceSpans" in data:
            for resource_span in data.get("resourceSpans", []):
                resource_attrs = attrs_to_dict(resource_span.get("resource", {}).get("attributes", []))
                service = resource_attrs.get("service.name")
                for group_key in ("scopeSpans", "instrumentationLibrarySpans"):
                    for scope in resource_span.get(group_key, []):
                        for span in scope.get("spans", []):
                            spans.append(normalize_span(span, service))
            return spans
        if "spans" in data and isinstance(data["spans"], list):
            spans.extend(normalize_span(span, data.get("service")) for span in data["spans"])
        for value in data.values():
            if isinstance(value, (dict, list)):
                spans.extend(iter_spans(value))
    elif isinstance(data, list):
        for item in data:
            spans.extend(iter_spans(item))
    return spans


def normalize_span(span: dict[str, Any], service_hint: str | None = None) -> dict[str, Any]:
    attrs = span.get("attributes", {})
    if isinstance(attrs, list):
        attrs = attrs_to_dict(attrs)
    name = str(span.get("name", ""))
    return {
        "name": name,
        "service": span.get("service") or span.get("serviceName") or service_hint or attrs.get("service.name"),
        "target_service": attrs.get("peer.service") or attrs.get("server.address") or attrs.get("net.peer.name"),
        "path": attrs.get("http.route")
        or attrs.get("http.target")
        or attrs.get("url.path")
        or path_from_span_name(name),
        "topic": attrs.get("messaging.destination.name")
        or attrs.get("messaging.destination")
        or attrs.get("messaging.kafka.topic"),
    }


def attr_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    if "arrayValue" in value:
        return [attr_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return attrs_to_dict(value["kvlistValue"].get("values", []))
    return value


def attrs_to_dict(attrs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        str(item["key"]): attr_value(item.get("value"))
        for item in attrs
        if isinstance(item, dict) and item.get("key") is not None
    }


def node_signatures(nodes: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    signatures: dict[tuple[str, str], dict[str, Any]] = {}
    for node in nodes:
        service = str(node.get("service", ""))
        for key in ("path", "topic"):
            if node.get(key):
                signatures[(service, str(node[key]))] = node
                signatures[("", str(node[key]))] = node
        for topic in node.get("topics", []):
            signatures[(service, str(topic))] = node
            signatures[("", str(topic))] = node
    return signatures


def match_span_node(
    span: dict[str, Any], signatures: dict[tuple[str, str], dict[str, Any]], role: str
) -> dict[str, Any] | None:
    service = str(span.get("service") if role == "source" else span.get("target_service") or "")
    candidates = [span.get("topic"), span.get("path"), span.get("name")]
    for candidate in candidates:
        if not candidate:
            continue
        for key in ((service, str(candidate)), ("", str(candidate))):
            if key in signatures:
                return signatures[key]
    if role == "source" and service:
        for (_, _), node in signatures.items():
            if node.get("service") == service:
                return node
    return None


def stub_node(span: dict[str, Any]) -> dict[str, Any]:
    service = span.get("target_service") or span.get("service") or "unknown"
    topic = span.get("topic")
    path = span.get("path")
    digest = hashlib.sha1(f"{service}:{topic or path or span.get('name')}".encode()).hexdigest()[:10]
    label = "KafkaConsumer" if topic else "Endpoint"
    props: dict[str, Any] = {"path": path} if path else {}
    if topic:
        props.update({"topics": [topic], "message_role": "consumer", "bus": "trace"})
    return {
        "id": f"{service}:otel:{digest}",
        "label": label,
        "service": service,
        "source": "otel-trace",
        "confidence": "low",
        **props,
    }


def trace_edge_type(span: dict[str, Any]) -> str:
    return "KAFKA_DELIVERS" if span.get("topic") else "CROSSES_TIER"


def path_from_span_name(name: str) -> str | None:
    match = re.search(r"\b(/[A-Za-z0-9_./{}-]+)", name)
    return match.group(1) if match else None
