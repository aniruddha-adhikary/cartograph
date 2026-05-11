"""HTTP cross-tier linker: connects HttpCall nodes to Endpoint nodes."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from ..graph import Edge, Graph, Node
from ..version import __version__

# Collapses path-template segments to a single sentinel for hashtable lookup.
# Matches: {id}, :id, ${id}, <id>
_TEMPLATE_TOKEN = re.compile(r"(\{[^/{}]+\}|:[A-Za-z_][A-Za-z0-9_]*|\$\{[^/{}]+\}|<[^/<>]+>)")
_SENTINEL = "§"


def normalize_template(path: str) -> str:
    """Collapse path-template tokens so calls and endpoints align in a hashtable."""
    if not path:
        return path
    out = _TEMPLATE_TOKEN.sub(_SENTINEL, path)
    # Strip trailing slash for canonicalization, but preserve "/"
    if len(out) > 1 and out.endswith("/"):
        out = out[:-1]
    return out


def _is_template(path: str) -> bool:
    return bool(_TEMPLATE_TOKEN.search(path or ""))


def _join_paths(*parts: str) -> str:
    parts = tuple(p for p in parts if p)
    if not parts:
        return ""
    cleaned: list[str] = []
    for i, p in enumerate(parts):
        s = p.strip()
        if i == 0:
            cleaned.append(s.rstrip("/"))
        else:
            cleaned.append(s.strip("/"))
    joined = "/".join(x for x in cleaned if x != "")
    if parts[0].startswith("/") and not joined.startswith("/"):
        joined = "/" + joined
    return joined or "/"


def _resolve_endpoint_absolute_path(node: Node, graph: Graph, visited: set[str]) -> str:
    if node.id in visited:
        return node.properties.get("path", "") or ""
    visited.add(node.id)
    own_path = node.properties.get("path", "") or ""
    base_ref = node.properties.get("base_path_ref")
    if not base_ref:
        return own_path or "/"
    parent = graph.get_node(base_ref)
    if parent is None:
        return own_path or "/"
    parent_base = parent.properties.get("base_path", "")
    parent_chained = parent.properties.get("base_path_ref")
    if parent_chained:
        parent_base = _join_paths(
            _resolve_endpoint_absolute_path_as_base(parent, graph, visited),
            parent_base,
        )
    return _join_paths(parent_base, own_path)


def _resolve_endpoint_absolute_path_as_base(node: Node, graph: Graph, visited: set[str]) -> str:
    if node.id in visited:
        return node.properties.get("base_path", "") or ""
    visited.add(node.id)
    own_base = node.properties.get("base_path", "") or ""
    ref = node.properties.get("base_path_ref")
    if not ref:
        return own_base
    parent = graph.get_node(ref)
    if parent is None:
        return own_base
    return _join_paths(_resolve_endpoint_absolute_path_as_base(parent, graph, visited), own_base)


class HttpCrossTierLinker:
    name = "http_cross_tier"

    def run(self, graph: Graph) -> None:
        # Resolve absolute paths for all endpoints
        for endpoint in graph.by_label("Endpoint"):
            absolute = _resolve_endpoint_absolute_path(endpoint, graph, set())
            endpoint.properties["absolute_path"] = absolute

        # Index endpoints by (method, normalized_path)
        index: dict[tuple[str, str], list[Node]] = defaultdict(list)
        for endpoint in graph.by_label("Endpoint"):
            method = (endpoint.properties.get("http_method") or "").upper()
            absolute = endpoint.properties.get("absolute_path") or ""
            index[(method, normalize_template(absolute))].append(endpoint)

        # Emit CROSSES_TIER edges
        for call in graph.by_label("HttpCall"):
            method = (call.properties.get("http_method") or "").upper()
            raw_path = call.properties.get("path") or ""
            normalized = normalize_template(raw_path)
            candidates = index.get((method, normalized), [])
            for endpoint in candidates:
                endpoint_path = endpoint.properties.get("absolute_path") or ""
                literal_match = (
                    raw_path == endpoint_path
                    and not _is_template(raw_path)
                    and not _is_template(endpoint_path)
                )
                confidence = "high" if literal_match else "medium"
                edge_props: dict[str, Any] = {
                    "confidence": confidence,
                    "matched_method": method,
                    "matched_path": endpoint_path,
                    "provenance": {
                        "linker": self.name,
                        "engine_version": __version__,
                    },
                }
                graph.add_edge(Edge(
                    type="CROSSES_TIER",
                    from_id=call.id,
                    to_id=endpoint.id,
                    properties=edge_props,
                ))
