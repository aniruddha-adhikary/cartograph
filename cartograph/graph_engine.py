from __future__ import annotations

from typing import Any

from .lens_specs import normalize_query, run_kuzu_query_subset

try:
    import kuzu as _kuzu
    HAS_KUZU = True
except ImportError:
    HAS_KUZU = False


def kuzu_available() -> bool:
    return HAS_KUZU


def run_graph_lens(
    lens: dict[str, Any],
    graph_data: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query = normalize_query(lens["match"]["query"])
    merged_params = {**lens["match"].get("params", {}), **(params or {})}

    if HAS_KUZU:
        return _run_kuzu_native(query, graph_data, merged_params)

    result = run_kuzu_query_subset(graph_data, query, merged_params)
    returns = lens.get("emit", {}).get("returns", {})
    return {
        "nodes": result["nodes"],
        "edges": result["edges"],
        "rows": result["rows"],
        "mode": "kuzu-subset",
        "query": query,
        "returns": returns,
    }


def _run_kuzu_native(
    query: str, graph_data: dict[str, Any], params: dict[str, Any],
) -> dict[str, Any]:
    raise NotImplementedError(
        "Native KuzuDB execution is planned for a future release. "
        "The hand-rolled Cypher interpreter handles the supported query subset."
    )
