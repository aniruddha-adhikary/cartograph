from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .views import load_view_specs, run_view


def load_graph(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_report(
    graph: dict[str, Any], graph_path: str | None = None, view_specs: dict[str, Any] | None = None
) -> str:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    services = sorted({n.get("service") for n in nodes if n.get("service")})
    node_counts = Counter(n.get("label") for n in nodes)
    edge_counts = Counter(e.get("type") for e in edges)
    confidence = Counter([n.get("confidence") for n in nodes] + [e.get("confidence") for e in edges])

    cross_service = [e for e in edges if e.get("cross_repo")]

    lines = [
        "# Cartograph Graph Report",
        "",
        "## Summary",
        "",
        f"- Graph: `{graph_path or 'cartograph graph'}`",
        f"- Services: {len(services)}",
        f"- Nodes: {len(nodes)}",
        f"- Edges: {len(edges)}",
        f"- Cross-service edges: {len(cross_service)}",
        "",
        "## Services",
        "",
    ]
    lines.extend(f"- `{service}`" for service in services)
    lines.extend(["", "## Node Labels", ""])
    lines.extend(f"- `{label}`: {count}" for label, count in sorted(node_counts.items()))
    lines.extend(["", "## Edge Types", ""])
    lines.extend(f"- `{label}`: {count}" for label, count in sorted(edge_counts.items()))
    lines.extend(["", "## Confidence", ""])
    lines.extend(f"- `{label}`: {count}" for label, count in sorted(confidence.items()))

    specs = view_specs or load_view_specs()
    if specs:
        lines.extend(["", "## Configured Views", ""])
        for name, spec in sorted(specs.items()):
            try:
                result = run_view(graph, spec, {})
            except Exception as exc:
                lines.append(f"- `{name}`: unavailable ({exc})")
                continue
            lines.append(f"- `{name}`: {view_size(result)}")

    lines.extend(
        [
            "",
            "## Suggested Questions",
            "",
            "- Which configured view best answers this codebase question?",
            "- Which services have the most cross-service edges?",
            "- Which medium-confidence edges need review?",
            "- Which project layer should own missing interpretation?",
        ]
    )
    return "\n".join(lines) + "\n"


def format_edge_list(edges: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> list[str]:
    by_id = {n["id"]: n for n in nodes}
    output = []
    for item in edges:
        src = by_id.get(item["from"], {})
        dst = by_id.get(item["to"], {})
        detail = src.get("topic") or src.get("path") or dst.get("path") or ""
        output.append(
            f"- `{item['from_service']}` -> `{item['to_service']}` `{item['type']}` {detail} ({item.get('confidence')})"
        )
    return output


def write_report(graph_path: Path, report_path: Path) -> None:
    graph = load_graph(graph_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(graph, str(graph_path)), encoding="utf-8")


def view_size(result: Any) -> str:
    if isinstance(result, list):
        return f"{len(result)} item(s)"
    if isinstance(result, dict):
        return f"{len(result)} group(s)"
    return type(result).__name__


def service_summary(graph: dict[str, Any]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: {"nodes": 0, "edges_out": 0, "edges_in": 0})
    for node in graph.get("nodes", []):
        summary[node["service"]]["nodes"] += 1
    for edge in graph.get("edges", []):
        summary[edge["from_service"]]["edges_out"] += 1
        summary[edge["to_service"]]["edges_in"] += 1
    return dict(summary)
