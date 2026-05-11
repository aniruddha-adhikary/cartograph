"""codette CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import Engine
from .graph import Graph
from .version import __version__


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codette", description="codette extractor engine")
    sub = p.add_subparsers(dest="command", required=True)

    idx = sub.add_parser("index", help="Index a repository")
    idx.add_argument("--repo", required=True, help="Path to repository root")
    idx.add_argument("--packs", required=True, help="Path to packs directory")
    idx.add_argument("--out", required=True, help="Output graph.json path")
    idx.add_argument("--changed-files", default=None,
                     help="Comma-separated paths for incremental re-index")
    idx.add_argument("--engine-version-pin", default=None,
                     help=f"Expected engine version (current: {__version__})")
    return p


def _emit_metrics(report) -> None:
    payload = {
        "files_indexed": report.files_indexed,
        "nodes_emitted": report.nodes_emitted,
        "edges_emitted": report.edges_emitted,
        "wall_ms": round(report.wall_ms, 2),
        "per_pack": {
            name: {
                "files_matched": m.files_matched,
                "nodes_emitted": m.nodes_emitted,
                "edges_emitted": m.edges_emitted,
                "errors": m.errors,
            }
            for name, m in report.per_pack.items()
        },
        "errors": report.errors,
    }
    sys.stderr.write(json.dumps(payload, indent=2) + "\n")


def _cmd_index(args: argparse.Namespace) -> int:
    if args.engine_version_pin and args.engine_version_pin != __version__:
        sys.stderr.write(
            f"error: engine version mismatch (pinned={args.engine_version_pin}, "
            f"actual={__version__})\n"
        )
        return 2

    engine = Engine.from_packs(args.packs)

    existing_graph: Graph | None = None
    changed = None
    if args.changed_files:
        changed = [s for s in (p.strip() for p in args.changed_files.split(",")) if s]
        out_path = Path(args.out)
        if out_path.exists():
            existing_graph = Graph.from_json(out_path)
        else:
            sys.stderr.write(
                f"warning: --changed-files given but {args.out} does not exist; full index\n"
            )
            changed = None

    graph, report = engine.index(
        args.repo,
        changed_files=changed,
        existing_graph=existing_graph,
    )

    graph.to_json(args.out)
    _emit_metrics(report)

    # FR-6: exit 0 if any nodes emitted, exit 2 only if all packs failed
    if report.nodes_emitted == 0 and any(m.errors > 0 for m in report.per_pack.values()):
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "index":
        return _cmd_index(args)
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
