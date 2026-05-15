#!/usr/bin/env python3
"""Evaluate Cartograph against a real repository.

Usage:
    python scripts/eval_repo.py --repo <github-url> [--branch <branch>]

Clones the repo (if not already present), indexes it, and prints a
quality report showing what was found and what might be missing.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOS_DIR = Path(__file__).resolve().parent.parent / ".cartograph-real-repos"
OUT_DIR = Path(__file__).resolve().parent.parent / "cartograph-out"


def clone_or_update(url: str, branch: str | None = None) -> Path:
    name = url.rstrip("/").split("/")[-1].replace(".git", "")
    dest = REPOS_DIR / name
    if dest.exists():
        print(f"repo already cloned: {dest}")
        return dest
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1", url, str(dest)]
    if branch:
        cmd.extend(["--branch", branch])
    subprocess.run(cmd, check=True)
    return dest


def index_repo(workspace: Path, name: str) -> Path:
    out = OUT_DIR / f"{name}-graph.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "cartograph", "index",
         "--workspace", str(workspace),
         "--out", str(out)],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}", file=sys.stderr)
    return out


def analyze_graph(graph_path: Path) -> dict:
    data = json.loads(graph_path.read_text())
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    meta = data.get("meta", {})

    labels = {}
    for n in nodes:
        label = n.get("label", "unknown")
        labels[label] = labels.get(label, 0) + 1

    edge_types = {}
    for e in edges:
        t = e.get("type", "unknown")
        edge_types[t] = edge_types.get(t, 0) + 1

    services = sorted(set(n.get("service", "") for n in nodes if n.get("service")))
    sources = {}
    for n in nodes:
        s = n.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1

    confidence = {"high": 0, "medium": 0, "low": 0}
    for n in nodes:
        c = n.get("confidence", "unknown")
        if c in confidence:
            confidence[c] += 1

    cross_service = [e for e in edges if e.get("cross_repo") or e.get("from_service") != e.get("to_service")]

    return {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "services": services,
        "service_count": len(services),
        "node_labels": dict(sorted(labels.items(), key=lambda x: -x[1])),
        "edge_types": dict(sorted(edge_types.items(), key=lambda x: -x[1])),
        "sources": dict(sorted(sources.items(), key=lambda x: -x[1])),
        "confidence": confidence,
        "cross_service_edges": len(cross_service),
        "has_endpoints": labels.get("Endpoint", 0) > 0,
        "has_http_calls": labels.get("HttpCall", 0) > 0,
        "has_kafka": labels.get("KafkaProducer", 0) > 0 or labels.get("KafkaConsumer", 0) > 0,
        "has_database": labels.get("DatabaseQuery", 0) > 0,
        "has_cross_service": len(cross_service) > 0,
    }


def print_report(analysis: dict, name: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Cartograph Evaluation: {name}")
    print(f"{'=' * 60}")
    print(f"  Services:  {analysis['service_count']} ({', '.join(analysis['services'][:10])}{'...' if analysis['service_count'] > 10 else ''})")
    print(f"  Nodes:     {analysis['total_nodes']}")
    print(f"  Edges:     {analysis['total_edges']}")
    print(f"  Cross-svc: {analysis['cross_service_edges']}")
    print()
    print("  Node Labels:")
    for label, count in analysis["node_labels"].items():
        print(f"    {label:30s} {count:6d}")
    print()
    print("  Edge Types:")
    for etype, count in analysis["edge_types"].items():
        print(f"    {etype:30s} {count:6d}")
    print()
    print("  Sources:")
    for src, count in list(analysis["sources"].items())[:15]:
        print(f"    {src:40s} {count:6d}")
    print()
    print("  Confidence:")
    for level, count in analysis["confidence"].items():
        print(f"    {level:10s} {count:6d}")
    print()
    checks = [
        ("Endpoints found", analysis["has_endpoints"]),
        ("HTTP calls found", analysis["has_http_calls"]),
        ("Kafka found", analysis["has_kafka"]),
        ("Database queries found", analysis["has_database"]),
        ("Cross-service edges", analysis["has_cross_service"]),
    ]
    print("  Quality Checks:")
    for check, passed in checks:
        status = "PASS" if passed else "MISS"
        print(f"    [{status}] {check}")
    print(f"{'=' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch")
    parser.add_argument("--name")
    args = parser.parse_args()

    name = args.name or args.repo.rstrip("/").split("/")[-1].replace(".git", "")
    workspace = clone_or_update(args.repo, args.branch)
    graph_path = index_repo(workspace, name)

    if not graph_path.exists():
        print("indexing failed — no graph produced", file=sys.stderr)
        sys.exit(1)

    analysis = analyze_graph(graph_path)
    print_report(analysis, name)

    report_path = OUT_DIR / f"{name}-eval.json"
    report_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    print(f"evaluation saved to {report_path}")


if __name__ == "__main__":
    main()
