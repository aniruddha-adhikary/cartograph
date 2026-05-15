"""Cross-service linkers: HTTP and message bus edge creation, deduplication."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from .graph import Graph, edge_key
from .util import slug, normalize_path, edge

if TYPE_CHECKING:
    from .indexer import ServiceContext


def run_linkers(graph: Graph, services: list[ServiceContext], registry: dict[str, str]) -> None:
    endpoint_by_service_path: dict[tuple[str, str], dict[str, Any]] = {}
    app_name_to_service: dict[str, str] = {}
    topic_consumers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    config_defaults: dict[tuple[str, str], str] = {}

    for ctx in services:
        app_name_to_service[slug(ctx.name)] = ctx.name
        for app_name in ctx.application_names:
            app_name_to_service[slug(app_name)] = ctx.name

    for node_item in graph.nodes:
        if node_item["label"] == "Endpoint":
            endpoint_by_service_path[(node_item["service"], normalize_path(node_item.get("path", "")))] = node_item
        elif node_item.get("message_role") == "consumer":
            for topic in node_item.get("topics", []):
                topic_consumers.setdefault((node_item.get("bus", "default"), topic), []).append(node_item)
        elif node_item["label"] == "ConfigProperty" and node_item.get("default_value"):
            config_defaults[(node_item["service"], node_item["key"])] = node_item["default_value"]

    for producer in [n for n in graph.nodes if n.get("message_role") == "producer"]:
        topic = resolve_topic(producer, config_defaults)
        for consumer in topic_consumers.get((producer.get("bus", "default"), topic), []):
            if producer["service"] != consumer["service"]:
                graph.add_edge(
                    edge(
                        producer.get("delivery_edge", "MESSAGE_DELIVERS"),
                        producer,
                        consumer,
                        "high" if not producer.get("topic_var") else "medium",
                    )
                )

    for call in [n for n in graph.nodes if n["label"] == "HttpCall"]:
        host = slug(str(call.get("host") or call.get("host_var") or ""))
        target_service = registry.get(host) or app_name_to_service.get(host)
        if not target_service:
            continue
        endpoint = endpoint_by_service_path.get((target_service, normalize_path(call.get("path", ""))))
        if not endpoint:
            endpoint = first_endpoint_for_service(graph, target_service)
        if endpoint and call["service"] != endpoint["service"]:
            confidence = "high" if host in registry else "medium"
            graph.add_edge(edge("CROSSES_TIER", call, endpoint, confidence))


def dedup_call_sites(graph: Graph) -> None:
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    removed_ids: set[str] = set()
    for n in graph.nodes:
        if n.get("message_role") == "producer" or n["label"] == "HttpCall":
            key = (
                n["label"],
                n["service"],
                n.get("file"),
                n.get("line"),
                n.get("topic") or n.get("topic_var") or n.get("path"),
            )
            if key in seen:
                seen[key]["duplicate_count"] = seen[key].get("duplicate_count", 1) + 1
                removed_ids.add(n["id"])
                continue
            seen[key] = n
        kept.append(n)
    graph.nodes = kept
    graph.edges = [e for e in graph.edges if e["from"] not in removed_ids and e["to"] not in removed_ids]


def dedup_edges(graph: Graph) -> None:
    seen: set[tuple[str, str, str]] = set()
    kept: list[dict[str, Any]] = []
    for item in graph.edges:
        key = edge_key(item)
        if key not in seen:
            seen.add(key)
            kept.append(item)
    graph.edges = kept


def load_service_registry(path: "Path") -> dict[str, str]:
    from pathlib import Path as _Path
    if not path.exists():
        return {}
    registry: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([^:#]+)\s*:\s*([^#]+)", line)
        if m:
            registry[slug(m.group(1).strip())] = slug(m.group(2).strip())
    return registry


def resolve_topic(producer: dict[str, Any], config_defaults: dict[tuple[str, str], str]) -> str:
    topic = producer.get("topic")
    if topic and not (topic.startswith("{") and topic.endswith("}")):
        return topic
    topic_var = producer.get("topic_var")
    if topic_var:
        for (service, key), value in config_defaults.items():
            if service == producer["service"] and key.endswith(topic_var):
                return value
    return topic or "{unknown}"


def first_endpoint_for_service(graph: Graph, service: str) -> dict[str, Any] | None:
    for item in graph.nodes:
        if item["label"] == "Endpoint" and item["service"] == service:
            return item
    return None


def find_node(graph: Graph, node_id: str | None) -> dict[str, Any] | None:
    if not node_id:
        return None
    for item in graph.nodes:
        if item["id"] == node_id:
            return item
    return None
