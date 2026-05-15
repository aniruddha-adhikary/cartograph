from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .graph import Graph
from .util import slug


def import_cgc(path: Path, service: str | None = None) -> Graph:
    data = json.loads(path.read_text(encoding="utf-8"))
    service_name = slug(service or data.get("service") or data.get("repository") or path.stem)
    graph = Graph(meta={"version": 1, "source": "cgc-import", "service": service_name})
    id_map: dict[str, str] = {}

    for raw in data.get("nodes", []):
        old_id = str(raw.get("id") or raw.get("name") or len(id_map))
        label, props = map_cgc_node(raw)
        new_id = f"{service_name}:cgc:{old_id}"
        id_map[old_id] = new_id
        graph.add_node(
            {
                "id": new_id,
                "label": label,
                "service": service_name,
                "source": "cgc-import",
                "confidence": "low",
                **props,
            }
        )

    for raw in data.get("edges", []):
        from_id = id_map.get(str(raw.get("from") or raw.get("source")))
        to_id = id_map.get(str(raw.get("to") or raw.get("target")))
        if not from_id or not to_id:
            continue
        graph.add_edge(
            {
                "type": "CROSSES_TIER"
                if raw.get("label") == "CallEdge" or raw.get("type") == "CallEdge"
                else str(raw.get("type") or "CGC_EDGE"),
                "from": from_id,
                "to": to_id,
                "from_service": service_name,
                "to_service": service_name,
                "cross_repo": False,
                "confidence": "low",
            }
        )
    return graph


def map_cgc_node(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    raw_label = str(raw.get("label") or raw.get("type") or "")
    props = {k: v for k, v in raw.items() if k not in {"id", "label", "type"}}
    if raw_label == "Function" and ("http_method" in raw or "path" in raw):
        return "Endpoint", props
    if raw_label == "Function":
        props.setdefault("kind", "cgc-function")
        return "Component", props
    if raw_label == "Class":
        props.setdefault("kind", "cgc-class")
        return "Service", props
    if raw_label == "File":
        return "File", props
    return "CgcNode", {"cgc_label": raw_label, **props}
