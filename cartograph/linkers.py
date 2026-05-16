"""Cross-service linkers: HTTP and message bus edge creation, deduplication."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from .graph import Graph, edge_key
from .util import slug, normalize_path, edge

# Property names commonly emitted by source lenses when an annotation argument
# is a Java symbol reference (field_access / identifier) rather than a string
# literal. The constants pre-pass resolves these to their corresponding
# non-`_const` property names.
CONST_PROP_MAP = {
    "destination_const": "destination",
    "topic_const": "topic",
    "channel_const": "channel",
    "queue_const": "queue",
    "name_const": "name",
    "value_const": "value",
    "path_const": "path",
    "url_const": "url",
    "event_const": "event",
}

if TYPE_CHECKING:
    from typing import Protocol

    class ServiceCtx(Protocol):
        name: str
        application_names: set[str]


def run_linkers(graph: Graph, services: list[ServiceCtx], registry: dict[str, str]) -> None:
    endpoint_by_service_path: dict[tuple[str, str], dict[str, Any]] = {}
    app_name_to_service: dict[str, str] = {}
    topic_consumers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    config_defaults: dict[tuple[str, str], str] = {}
    unresolved: list[dict[str, Any]] = []

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
        consumers = topic_consumers.get((producer.get("bus", "default"), topic), [])
        if not consumers:
            unresolved.append({
                "kind": "no_consumer",
                "node_id": producer["id"],
                "service": producer["service"],
                "topic": topic,
                "bus": producer.get("bus", "default"),
                "hint": f"Producer publishes to '{topic}' but no consumer subscribes to it",
            })
            continue
        for consumer in consumers:
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
            raw_refs = {
                k: call[k]
                for k in ("host", "host_var", "url", "feign_args", "path")
                if call.get(k)
            }
            unresolved.append({
                "kind": "unresolved_host",
                "node_id": call["id"],
                "service": call["service"],
                "host_slug": host,
                "raw": raw_refs,
                "hint": f"HttpCall has references {raw_refs} but no service matched slug '{host}'",
                "known_services": sorted(app_name_to_service.keys()),
            })
            continue
        endpoint = endpoint_by_service_path.get((target_service, normalize_path(call.get("path", ""))))
        if not endpoint:
            endpoint = first_endpoint_for_service(graph, target_service)
        if endpoint and call["service"] != endpoint["service"]:
            confidence = "high" if host in registry else "medium"
            graph.add_edge(edge("CROSSES_TIER", call, endpoint, confidence))

    graph.meta.setdefault("unresolved", []).extend(unresolved)


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


def apply_constants_to_nodes(graph: Graph, constants_by_file: dict[str, dict[str, str]]) -> int:
    """For each node whose file has a constants map, resolve `*_const` props
    by looking up the symbol in the same-file constants. Sets the corresponding
    non-`_const` prop iff that prop isn't already set (truthy).

    Returns the number of props resolved. Generic — no framework knowledge.
    """
    resolved = 0
    for n in graph.nodes:
        file_path = n.get("file")
        if not file_path:
            continue
        consts = constants_by_file.get(file_path)
        if not consts:
            continue
        # iterate over snapshot since we may add keys
        for key in list(n.keys()):
            if not key.endswith("_const"):
                continue
            target_key = CONST_PROP_MAP.get(key)
            if not target_key:
                # Generic fallback: strip `_const` suffix.
                target_key = key[: -len("_const")]
            if n.get(target_key):
                continue
            raw = n.get(key)
            if not raw or not isinstance(raw, str):
                continue
            value = consts.get(raw)
            if value is None:
                # Try the unqualified leaf form too: "Foo.BAR" -> "BAR".
                leaf = raw.rsplit(".", 1)[-1]
                value = consts.get(leaf)
            if value is None:
                continue
            n[target_key] = value
            # If the node carries a `topics` list with only `{unknown}` or empty,
            # and we just resolved `topic`, also patch the list so downstream
            # message-bus matching works.
            if target_key == "topic":
                topics = n.get("topics")
                if isinstance(topics, list) and (not topics or topics in ([""], ["{unknown}"])):
                    n["topics"] = [value]
            resolved += 1
    return resolved


def link_injection(graph: Graph) -> None:
    """Emit INJECTS edges from Injection -> Component when injected_type matches
    a Component.name. Prefer same-service matches when multiple exist.

    Bonus: persistence-context Injections also try matching against
    PersistenceUnit.name and emit USES_PERSISTENCE_UNIT.
    """
    components_by_name: dict[str, list[dict[str, Any]]] = {}
    units_by_name: dict[str, list[dict[str, Any]]] = {}
    for n in graph.nodes:
        if n["label"] == "Component":
            name = n.get("name") or n.get("class_name")
            if name:
                components_by_name.setdefault(name, []).append(n)
                # Also index unqualified leaf for fully-qualified class names.
                leaf = name.rsplit(".", 1)[-1]
                if leaf != name:
                    components_by_name.setdefault(leaf, []).append(n)
        elif n["label"] == "PersistenceUnit":
            name = n.get("name") or n.get("unit_name")
            if name:
                units_by_name.setdefault(name, []).append(n)

    unresolved: list[dict[str, Any]] = []
    for inj in [n for n in graph.nodes if n["label"] == "Injection"]:
        injected_type = inj.get("injected_type")
        if not injected_type:
            continue
        leaf = injected_type.rsplit(".", 1)[-1]
        candidates = components_by_name.get(injected_type) or components_by_name.get(leaf) or []
        target = _prefer_same_service(candidates, inj.get("service"))
        if target is not None:
            graph.add_edge({
                "type": "INJECTS",
                "from": inj["id"],
                "to": target["id"],
                "from_service": inj["service"],
                "to_service": target["service"],
                "cross_repo": inj["service"] != target["service"],
                "target_class": inj.get("target_class", ""),
                "injected_type": injected_type,
                "injection_kind": inj.get("kind", ""),
                "source": "linker:link_injection",
                "confidence": inj.get("confidence", "medium"),
            })
        else:
            unresolved.append({
                "kind": "no_inject_target",
                "node_id": inj["id"],
                "service": inj.get("service"),
                "injected_type": injected_type,
                "hint": f"Injection of '{injected_type}' has no matching Component",
            })

        if inj.get("kind") == "persistence-context":
            unit_name = inj.get("unit_name") or injected_type
            unit_candidates = units_by_name.get(unit_name) or units_by_name.get(unit_name.rsplit(".", 1)[-1]) or []
            unit_target = _prefer_same_service(unit_candidates, inj.get("service"))
            if unit_target is not None:
                graph.add_edge({
                    "type": "USES_PERSISTENCE_UNIT",
                    "from": inj["id"],
                    "to": unit_target["id"],
                    "from_service": inj["service"],
                    "to_service": unit_target["service"],
                    "cross_repo": inj["service"] != unit_target["service"],
                    "unit_name": unit_name,
                    "source": "linker:link_injection",
                    "confidence": "medium",
                })

    graph.meta.setdefault("unresolved", []).extend(unresolved)


def link_entity_relation(graph: Graph) -> None:
    """Emit RELATES_TO edges between owner Entity and target Entity using
    EntityRelation nodes as the source of truth for kind/field_name/mapped_by.
    """
    entities_by_name: dict[str, list[dict[str, Any]]] = {}
    for n in graph.nodes:
        if n["label"] == "Entity":
            name = n.get("name") or n.get("class_name")
            if name:
                entities_by_name.setdefault(name, []).append(n)
                leaf = name.rsplit(".", 1)[-1]
                if leaf != name:
                    entities_by_name.setdefault(leaf, []).append(n)

    unresolved: list[dict[str, Any]] = []
    for rel in [n for n in graph.nodes if n["label"] == "EntityRelation"]:
        owner_class = rel.get("owner_class")
        target_type = rel.get("target_type")
        if not owner_class or not target_type:
            continue
        # Strip common collection generics: List<Foo> -> Foo, Set<Foo> -> Foo, etc.
        target_leaf = _unwrap_collection(target_type)
        owner_candidates = entities_by_name.get(owner_class) or entities_by_name.get(owner_class.rsplit(".", 1)[-1]) or []
        target_candidates = entities_by_name.get(target_leaf) or entities_by_name.get(target_leaf.rsplit(".", 1)[-1]) or []
        owner = _prefer_same_service(owner_candidates, rel.get("service"))
        target = _prefer_same_service(target_candidates, rel.get("service"))
        if owner is None or target is None:
            unresolved.append({
                "kind": "no_entity_target",
                "node_id": rel["id"],
                "service": rel.get("service"),
                "owner_class": owner_class,
                "target_type": target_type,
                "hint": f"EntityRelation {owner_class}.{rel.get('field_name')} -> {target_type} unresolved",
            })
            continue
        graph.add_edge({
            "type": "RELATES_TO",
            "from": owner["id"],
            "to": target["id"],
            "from_service": owner["service"],
            "to_service": target["service"],
            "cross_repo": owner["service"] != target["service"],
            "kind": rel.get("kind", ""),
            "field_name": rel.get("field_name", ""),
            "mapped_by": rel.get("mapped_by", ""),
            "relation_node_id": rel["id"],
            "source": "linker:link_entity_relation",
            "confidence": rel.get("confidence", "medium"),
        })

    graph.meta.setdefault("unresolved", []).extend(unresolved)


def link_cdi_event(graph: Graph) -> None:
    """Emit EVENT_DELIVERS edges from EventProducer to EventConsumer on matching
    event_type. Cartesian if multiple producers + consumers exist for a type.
    """
    consumers_by_type: dict[str, list[dict[str, Any]]] = {}
    for n in graph.nodes:
        if n["label"] == "EventConsumer":
            event_type = n.get("event_type")
            if event_type:
                consumers_by_type.setdefault(event_type, []).append(n)
                leaf = event_type.rsplit(".", 1)[-1]
                if leaf != event_type:
                    consumers_by_type.setdefault(leaf, []).append(n)

    unresolved: list[dict[str, Any]] = []
    for prod in [n for n in graph.nodes if n["label"] == "EventProducer"]:
        event_type = prod.get("event_type")
        if not event_type:
            continue
        consumers = consumers_by_type.get(event_type) or consumers_by_type.get(event_type.rsplit(".", 1)[-1]) or []
        if not consumers:
            unresolved.append({
                "kind": "no_event_consumer",
                "node_id": prod["id"],
                "service": prod.get("service"),
                "event_type": event_type,
                "hint": f"EventProducer for '{event_type}' has no consumer",
            })
            continue
        for cons in consumers:
            graph.add_edge({
                "type": "EVENT_DELIVERS",
                "from": prod["id"],
                "to": cons["id"],
                "from_service": prod["service"],
                "to_service": cons["service"],
                "cross_repo": prod["service"] != cons["service"],
                "event_type": event_type,
                "bus": "cdi-event",
                "source": "linker:link_cdi_event",
                "confidence": "medium",
            })

    graph.meta.setdefault("unresolved", []).extend(unresolved)


def link_endpoint_param(graph: Graph) -> None:
    """Emit HAS_PARAM edges from Endpoint to EndpointParam when the param's
    owner_class.owner_method matches Endpoint.handler.
    """
    endpoints_by_handler: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for n in graph.nodes:
        if n["label"] == "Endpoint":
            handler = n.get("handler")
            if handler:
                endpoints_by_handler.setdefault((n.get("service", ""), handler), []).append(n)

    unresolved: list[dict[str, Any]] = []
    for param in [n for n in graph.nodes if n["label"] == "EndpointParam"]:
        owner_class = param.get("owner_class") or ""
        owner_method = param.get("owner_method") or ""
        if not owner_class or not owner_method:
            continue
        handler = f"{owner_class}.{owner_method}"
        candidates = endpoints_by_handler.get((param.get("service", ""), handler))
        if not candidates:
            # Try cross-service as a fallback.
            candidates = [
                ep for (_svc, h), eps in endpoints_by_handler.items()
                if h == handler for ep in eps
            ]
        if not candidates:
            unresolved.append({
                "kind": "no_endpoint_for_param",
                "node_id": param["id"],
                "service": param.get("service"),
                "handler": handler,
                "hint": f"EndpointParam refers to handler '{handler}' with no Endpoint",
            })
            continue
        for ep in candidates:
            graph.add_edge({
                "type": "HAS_PARAM",
                "from": ep["id"],
                "to": param["id"],
                "from_service": ep["service"],
                "to_service": param["service"],
                "cross_repo": ep["service"] != param["service"],
                "kind": param.get("kind", ""),
                "name": param.get("name", ""),
                "source": "linker:link_endpoint_param",
                "confidence": "high",
            })

    graph.meta.setdefault("unresolved", []).extend(unresolved)


def _prefer_same_service(candidates: list[dict[str, Any]], service: str | None) -> dict[str, Any] | None:
    if not candidates:
        return None
    if service:
        for c in candidates:
            if c.get("service") == service:
                return c
    return candidates[0]


def _unwrap_collection(type_text: str) -> str:
    """Pull the inner type out of `List<Foo>` / `Set<Foo>` / `Collection<Foo>` /
    `Map<K,Foo>`. Returns the input unchanged when no generic wrapper is present.
    """
    m = re.search(r"<([^<>]+)>$", type_text.strip())
    if not m:
        return type_text.strip()
    inner = m.group(1).strip()
    # For Map<K, V>, take V (last comma-separated arg).
    if "," in inner:
        inner = inner.rsplit(",", 1)[-1].strip()
    return inner


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
