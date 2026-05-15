"""Service discovery: finding service roots and reading service configuration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .util import slug

SOURCE_EXTS = {".java", ".js", ".jsx", ".ts", ".tsx", ".yml", ".yaml", ".properties", ".xml", ".jsp", ".jspx", ".tag", ".tld", ".sql", ".json"}


def discover_service_roots(workspace: Path) -> list[Path]:
    children = [p for p in sorted(workspace.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    service_children = [p for p in children if looks_like_service(p)]
    if service_children:
        return service_children
    return [workspace]


def looks_like_service(path: Path) -> bool:
    if (path / "cartograph.yaml").exists() or (path / "package.json").exists() or (path / "pom.xml").exists():
        return True
    return any(p.suffix in SOURCE_EXTS for p in path.rglob("*") if p.is_file())


def service_name(root: Path) -> str:
    name = service_config(root).get("name")
    if name:
        return slug(str(name))
    pkg = root / "package.json"
    if pkg.exists():
        try:
            name = json.loads(pkg.read_text(encoding="utf-8")).get("name")
            if name:
                return slug(str(name).split("/")[-1])
        except json.JSONDecodeError:
            pass
    return slug(root.name)


def service_config(root: Path) -> dict[str, Any]:
    cfg = root / "cartograph.yaml"
    result: dict[str, Any] = {"exclude": []}
    if cfg.exists():
        parsed = parse_config_file(cfg)
        result.update(parsed)
        excludes: list[str] = []
        for key in ("exclude", "excludes", "additional_excludes"):
            value = parsed.get(key)
            if isinstance(value, list):
                excludes.extend(str(item) for item in value)
            elif isinstance(value, str):
                excludes.append(value)
        result["exclude"] = excludes
    return result


def parse_config_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    return parse_simple_yaml(text)


def parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any], dict[str, Any] | None, str | None]] = [(-1, root, None, None)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(container, list):
                parent = stack[-1][2]
                key = stack[-1][3]
                if isinstance(parent, dict) and key:
                    parent[key] = []
                    container = parent[key]
                    stack[-1] = (stack[-1][0], container, parent, key)
            if isinstance(container, list):
                container.append(parse_scalar(line[2:].strip()))
            continue
        if ":" not in line or not isinstance(container, dict):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            container[key] = parse_scalar(value)
            continue
        container[key] = {}
        stack.append((indent, container[key], container, key))
    return root


def parse_scalar(value: str) -> Any:
    value = value.strip().strip("'\"")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("[") and value.endswith("]"):
        return [parse_scalar(item.strip()) for item in value[1:-1].split(",") if item.strip()]
    return value
