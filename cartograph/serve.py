from __future__ import annotations

import json
import sys
from pathlib import Path

from .lens_specs import load_lens_specs
from .plugins import run_plugin
from .query import (
    cgc_tool,
    coverage_report,
    cross_service_edges,
    endpoints_in_service,
    explain_flow,
    find_callees,
    find_callers,
    flow,
    kafka_topics,
    lens,
    list_lenses,
    load_graph,
    search,
)
from .tools import tool_catalog
from .views import load_view_specs, run_view


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    graph_path = Path(args[0]) if args else Path("cartograph-out/graph.json")
    graph = load_graph(graph_path)
    view_specs = load_view_specs(workspace=Path("."))
    lens_specs = load_lens_specs(workspace=Path("."))
    for line in sys.stdin:
        try:
            result: object
            request = json.loads(line)
            method = request.get("method")
            params = request.get("params", {})
            if method == "tools/list":
                result = tool_catalog()
            elif method == "tools/call":
                result = dispatch(graph, view_specs, lens_specs, params["name"], params.get("arguments", {}))
            else:
                result = dispatch(graph, view_specs, lens_specs, method, params)
            print(json.dumps({"id": request.get("id"), "result": result}), flush=True)
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), flush=True)
    return 0


def dispatch(graph: dict, view_specs: dict, lens_specs: dict, method: str, params: dict) -> object:
    bare_method = method.removeprefix("cartograph.")
    if bare_method == "query":
        name = params["name"]
        if name not in view_specs:
            raise ValueError(f"unknown view {name}")
        return run_view(graph, view_specs[name], params.get("params", {}))
    if bare_method == "flow":
        return flow(graph, params["anchor"], params.get("depth", 8))
    if bare_method == "find_callers":
        return find_callers(graph, params["symbol"])
    if bare_method == "find_callees":
        return find_callees(graph, params["symbol"])
    if bare_method == "endpoints_in_service":
        return endpoints_in_service(graph, params["service"], params.get("path"))
    if bare_method == "cross_service_edges":
        return cross_service_edges(graph, params.get("filter", {}))
    if bare_method == "kafka_topics":
        return kafka_topics(graph, params.get("filter", {}))
    if bare_method == "coverage_report":
        return coverage_report(graph, params.get("threshold", 0.8))
    if bare_method == "search":
        return search(
            graph, params["query"], params.get("fallback", True), params.get("limit", 10), params.get("label")
        )
    if bare_method == "explain_flow":
        return explain_flow(graph, params["anchor"], params.get("depth", 8))
    if bare_method == "lens":
        if params.get("list"):
            return list_lenses(graph, lens_specs)
        return lens(graph, params["name"], lens_specs, params=params.get("params", {}))
    if method.startswith("cgc."):
        return cgc_tool(graph, method, params)
    if bare_method == "run_plugin":
        return run_plugin(graph, Path(params["plugin"]), params.get("args", {}))
    raise ValueError(f"unknown method {method}")


if __name__ == "__main__":
    raise SystemExit(main())
