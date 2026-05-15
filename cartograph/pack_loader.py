"""Pack configuration loading, merging, and normalization."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from .schema import validate_pack_config


def load_pack_config(name: str, workspace: Path, packs_dir: Path | list[Path] | None = None) -> dict[str, Any]:
    bundled = json.loads(resources.files("cartograph").joinpath(f"packs/{name}.json").read_text(encoding="utf-8"))
    validate_pack_config(bundled, name=f"bundled:{name}")
    candidates: list[Path] = []
    pack_dirs_value = [packs_dir] if isinstance(packs_dir, Path) else packs_dir or []
    candidates.append(workspace / ".cartograph" / "packs" / f"{name}.json")
    for item in pack_dirs_value:
        candidates.append(item / f"{name}.json")
    candidates = unique_paths(candidates)
    for path in candidates:
        if path.exists():
            overlay = json.loads(path.read_text(encoding="utf-8"))
            validate_pack_config(overlay, name=str(path), partial=True)
            bundled = deep_merge(bundled, overlay)
            validate_pack_config(bundled, name=f"merged:{name}")
    return normalize_pack_config(bundled)


def normalize_pack_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    if "kafka" in normalized:
        kafka = normalized["kafka"]
        kafka_bus = {
            "name": "kafka",
            "listener_annotation": kafka.get("listener_annotation", "@KafkaListener"),
            "producer_methods": kafka.get("producer_methods", [".send("]),
            "config_annotation": kafka.get("config_annotation", "@Value"),
            "producer_label": "KafkaProducer",
            "consumer_label": "KafkaConsumer",
            "consumer_class_label": "KafkaConsumerClass",
            "handler_edge": "HANDLES_KAFKA",
            "delivery_edge": "KAFKA_DELIVERS",
            "source": "pack:spring-kafka",
            "config_source": "pack:spring-kafka-config",
        }
        buses = [bus for bus in normalized.get("message_buses", []) if bus.get("name") != "kafka"]
        normalized["message_buses"] = [*buses, kafka_bus]
    return normalized


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = merge_lists(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_lists(base: list[Any], overlay: list[Any]) -> list[Any]:
    if all(isinstance(item, dict) and "name" in item for item in [*base, *overlay]):
        by_name = {item["name"]: dict(item) for item in base}
        order = [item["name"] for item in base]
        for item in overlay:
            item_name = item["name"]
            if item_name in by_name:
                by_name[item_name] = deep_merge(by_name[item_name], item)
            else:
                order.append(item_name)
                by_name[item_name] = dict(item)
        return [by_name[item_name] for item_name in order]
    merged = list(base)
    for item in overlay:
        if item not in merged:
            merged.append(item)
    return merged


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique
