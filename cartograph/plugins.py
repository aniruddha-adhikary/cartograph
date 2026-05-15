from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def run_plugin(graph: dict[str, Any], plugin_path: Path, args: dict[str, Any] | None = None) -> Any:
    plugin_path = plugin_path.resolve()
    spec = importlib.util.spec_from_file_location("cartograph_project_plugin", plugin_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load plugin: {plugin_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise ValueError(f"plugin {plugin_path} must define run(graph, args)")
    return module.run(graph, args or {})


def parse_plugin_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = raw.strip()
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)
