from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


class LensValidationError(ValueError):
    pass


def validate_lens(lens: dict[str, Any]) -> None:
    if not isinstance(lens, dict):
        raise LensValidationError("lens must be a dict")
    if not lens.get("name"):
        raise LensValidationError("lens must have a non-empty 'name'")
    scope = lens.get("scope")
    if scope not in ("source", "graph", "resolve"):
        raise LensValidationError(f"lens scope must be 'source', 'graph', or 'resolve', got '{scope}'")
    if not isinstance(lens.get("match"), dict):
        raise LensValidationError("lens must have a 'match' dict")
    if scope == "resolve":
        if not isinstance(lens.get("set"), dict):
            raise LensValidationError("resolve lens must have a 'set' dict")
        return
    if not isinstance(lens.get("emit"), dict):
        raise LensValidationError("lens must have an 'emit' dict")
    if scope == "source":
        _validate_source_lens(lens)
    else:
        _validate_graph_lens(lens)


def _validate_source_lens(lens: dict[str, Any]) -> None:
    match = lens["match"]
    if "files" not in match or not isinstance(match["files"], list):
        raise LensValidationError("source lens match must include 'files' list")
    emit = lens["emit"]
    if not emit.get("label"):
        raise LensValidationError("source lens emit must include 'label'")
    if not isinstance(emit.get("schema", {}), dict):
        raise LensValidationError("source lens emit.schema must be a dict")
    if not isinstance(emit.get("values", {}), dict):
        raise LensValidationError("source lens emit.values must be a dict")


def _validate_graph_lens(lens: dict[str, Any]) -> None:
    match = lens["match"]
    if not match.get("query"):
        raise LensValidationError("graph lens match must include 'query'")


def load_lens_file(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    for lens in data:
        validate_lens(lens)
    return data


def load_lens_dir(directory: Path) -> list[dict[str, Any]]:
    lenses: list[dict[str, Any]] = []
    if not directory.exists():
        return lenses
    for path in sorted(directory.glob("*.json")):
        lenses.extend(load_lens_file(path))
    return lenses


def load_builtin_lenses() -> list[dict[str, Any]]:
    lenses: list[dict[str, Any]] = []
    builtin_dir = resources.files("cartograph").joinpath("lens_defs")
    for item in sorted(builtin_dir.iterdir()):
        if item.name.endswith(".json"):
            data = json.loads(item.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = [data]
            for lens in data:
                validate_lens(lens)
                lenses.append(lens)
    return lenses
