from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cgc import import_cgc
from .discover import write_discovery
from .indexer import index_workspace
from .install import install, uninstall
from .layers import layer_dirs, lens_dirs, pack_dirs, view_dirs
from .lens_specs import load_lens_specs
from .plugins import parse_plugin_args, run_plugin
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
from .report import write_report
from .tools import tool_catalog
from .trace import import_trace
from .verify import verify_graph
from .views import load_view_specs, run_view


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cartograph")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Index a workspace into a federated graph JSON file")
    p_index.add_argument("--workspace", required=True)
    p_index.add_argument("--out", required=True)
    p_index.add_argument("--registry")
    p_index.add_argument("--report")
    p_index.add_argument("--packs-dir")
    p_index.add_argument("--layer-dir", action="append", default=[])
    p_index.add_argument("--include-test-paths", action="store_true")

    p_verify = sub.add_parser("verify", help="Verify a graph against an expectation suite")
    p_verify.add_argument("--graph", required=True)
    p_verify.add_argument("--suite", required=True)

    p_discover = sub.add_parser("discover-packs", help="Discover candidate project pack config")
    p_discover.add_argument("--workspace", required=True)
    p_discover.add_argument("--out", default=".cartograph/discovery.json")

    p_cgc = sub.add_parser("import-cgc", help="Import a CGC JSON graph export")
    p_cgc.add_argument("--input", required=True)
    p_cgc.add_argument("--out", required=True)
    p_cgc.add_argument("--service")

    p_trace = sub.add_parser("import-trace", help="Import an OTLP JSON trace into a graph")
    p_trace.add_argument("--graph", required=True)
    p_trace.add_argument("--otlp", required=True)
    p_trace.add_argument("--out", required=True)

    p_install = sub.add_parser("install", help="Install Cartograph agent instructions")
    p_install.add_argument("--platform", choices=["codex", "claude"], default="codex")
    p_install.add_argument("--project", default=".")

    p_uninstall = sub.add_parser("uninstall", help="Remove Cartograph agent instructions")
    p_uninstall.add_argument("--platform", choices=["codex", "claude"], default="codex")
    p_uninstall.add_argument("--project", default=".")

    p_report = sub.add_parser("report", help="Generate GRAPH_REPORT.md for a graph")
    p_report.add_argument("--graph", required=True)
    p_report.add_argument("--out", required=True)

    p_query = sub.add_parser("query", help="Run a configured graph view")
    p_query.add_argument("--graph", required=True)
    p_query.add_argument("--name", required=True)
    p_query.add_argument("--views-dir")
    p_query.add_argument("--layer-dir", action="append", default=[])
    p_query.add_argument("--workspace")
    p_query.add_argument("--param", action="append", default=[])

    p_plugin = sub.add_parser("run-plugin", help="Run a local project plugin against a graph")
    p_plugin.add_argument("--graph", required=True)
    p_plugin.add_argument("--plugin", required=True)
    p_plugin.add_argument("--args")
    p_plugin.add_argument("--allow-plugin", action="store_true")

    p_flow = sub.add_parser("flow", help="Return a flow subgraph from an anchor")
    p_flow.add_argument("--graph", required=True)
    p_flow.add_argument("--anchor", required=True)
    p_flow.add_argument("--depth", type=int, default=8)

    p_explain = sub.add_parser("explain", help="Explain a flow from an anchor")
    p_explain.add_argument("--graph", required=True)
    p_explain.add_argument("--anchor", required=True)

    p_find_callers = sub.add_parser("find-callers", help="Return callers for a symbol, node, path, or topic")
    p_find_callers.add_argument("--graph", required=True)
    p_find_callers.add_argument("--symbol", required=True)

    p_find_callees = sub.add_parser("find-callees", help="Return callees for a symbol, node, path, or topic")
    p_find_callees.add_argument("--graph", required=True)
    p_find_callees.add_argument("--symbol", required=True)

    p_endpoints = sub.add_parser("endpoints-in-service", help="List endpoints in one service")
    p_endpoints.add_argument("--graph", required=True)
    p_endpoints.add_argument("--service", required=True)
    p_endpoints.add_argument("--path")

    p_cross = sub.add_parser("cross-service-edges", help="List cross-service HTTP and message edges")
    p_cross.add_argument("--graph", required=True)
    p_cross.add_argument("--from-service")
    p_cross.add_argument("--to-service")

    p_topics = sub.add_parser("kafka-topics", help="List message topics grouped by topic")
    p_topics.add_argument("--graph", required=True)
    p_topics.add_argument("--producer-service")
    p_topics.add_argument("--consumer-service")
    p_topics.add_argument("--bus")

    p_coverage = sub.add_parser("coverage-report", help="Return per-service coverage/source breakdown")
    p_coverage.add_argument("--graph", required=True)
    p_coverage.add_argument("--threshold", type=float, default=0.8)

    p_search = sub.add_parser("search", help="Search graph nodes by exact match with deterministic fallback")
    p_search.add_argument("--graph", required=True)
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--fallback", choices=["true", "false"], default="true")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--label")

    p_lens = sub.add_parser("lens", help="Return a named generated or configured lens")
    p_lens.add_argument("action", nargs="?", choices=["list"])
    p_lens.add_argument("--graph", required=True)
    p_lens.add_argument("--name")
    p_lens.add_argument("--params", default="{}")
    p_lens.add_argument("--workspace")
    p_lens.add_argument("--lenses-dir")
    p_lens.add_argument("--layer-dir", action="append", default=[])

    p_cgc_tool = sub.add_parser("cgc-tool", help="Run a CGC-compatible query adapter")
    p_cgc_tool.add_argument("--graph", required=True)
    p_cgc_tool.add_argument("--tool", required=True)
    p_cgc_tool.add_argument("--params", default="{}")

    p_serve = sub.add_parser("serve", help="Run the JSON-lines MCP-style query server")
    p_serve.add_argument("--graph", default="cartograph-out/graph.json")

    sub.add_parser("tools", help="List Cartograph agent-facing tools and CLI examples")

    args = parser.parse_args(argv)

    if args.command == "index":
        graph = index_workspace(
            Path(args.workspace),
            registry_path=Path(args.registry) if args.registry else None,
            include_test_paths=args.include_test_paths,
            packs_dir=[
                *pack_dirs(layer_dirs(Path(args.workspace), [Path(item) for item in args.layer_dir])),
                *([Path(args.packs_dir)] if args.packs_dir else []),
            ],
        )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.report:
            write_report(out, Path(args.report))
        print(f"indexed {len(graph.nodes)} nodes / {len(graph.edges)} edges -> {out}")
        return 0

    if args.command == "verify":
        errors = verify_graph(Path(args.graph), Path(args.suite))
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        print("verification passed")
        return 0

    if args.command == "discover-packs":
        write_discovery(Path(args.workspace), Path(args.out))
        print(f"wrote {args.out}")
        return 0

    if args.command == "import-cgc":
        cgc_graph = import_cgc(Path(args.input), service=args.service)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cgc_graph.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"imported {len(cgc_graph.nodes)} CGC nodes / {len(cgc_graph.edges)} edges -> {out}")
        return 0

    if args.command == "import-trace":
        trace_graph = import_trace(load_graph(Path(args.graph)), Path(args.otlp))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(trace_graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"imported trace -> {out}")
        return 0

    if args.command == "install":
        paths = install(args.platform, Path(args.project))
        for path in paths:
            print(f"wrote {path}")
        return 0

    if args.command == "uninstall":
        paths = uninstall(args.platform, Path(args.project))
        for path in paths:
            print(f"removed/updated {path}")
        return 0

    if args.command == "report":
        write_report(Path(args.graph), Path(args.out))
        print(f"wrote {args.out}")
        return 0

    if args.command == "query":
        params = dict(param.split("=", 1) for param in args.param)
        query_graph = load_graph(Path(args.graph))
        layers = layer_dirs(Path(args.workspace) if args.workspace else None, [Path(item) for item in args.layer_dir])
        dirs = view_dirs(layers)
        if args.views_dir:
            dirs.append(Path(args.views_dir))
        specs = load_view_specs(
            workspace=Path(args.workspace) if args.workspace else None,
            views_dir=dirs,
        )
        if args.name not in specs:
            raise SystemExit(f"unknown view {args.name}; available: {', '.join(sorted(specs))}")
        print(json.dumps(run_view(query_graph, specs[args.name], params), indent=2, sort_keys=True))
        return 0

    if args.command == "run-plugin":
        if not args.allow_plugin:
            raise SystemExit(
                "run-plugin executes local Python; re-run with --allow-plugin after reviewing the plugin file"
            )
        plugin_graph = load_graph(Path(args.graph))
        print(
            json.dumps(
                run_plugin(plugin_graph, Path(args.plugin), parse_plugin_args(args.args)), indent=2, sort_keys=True
            )
        )
        return 0

    if args.command == "flow":
        print(json.dumps(flow(load_graph(Path(args.graph)), args.anchor, args.depth), indent=2, sort_keys=True))
        return 0

    if args.command == "explain":
        print(json.dumps(explain_flow(load_graph(Path(args.graph)), args.anchor), indent=2, sort_keys=True))
        return 0

    if args.command == "find-callers":
        print(json.dumps(find_callers(load_graph(Path(args.graph)), args.symbol), indent=2, sort_keys=True))
        return 0

    if args.command == "find-callees":
        print(json.dumps(find_callees(load_graph(Path(args.graph)), args.symbol), indent=2, sort_keys=True))
        return 0

    if args.command == "endpoints-in-service":
        print(
            json.dumps(
                endpoints_in_service(load_graph(Path(args.graph)), args.service, args.path), indent=2, sort_keys=True
            )
        )
        return 0

    if args.command == "cross-service-edges":
        filter_args = {"from_service": args.from_service, "to_service": args.to_service}
        print(
            json.dumps(
                cross_service_edges(load_graph(Path(args.graph)), {k: v for k, v in filter_args.items() if v}),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "kafka-topics":
        filter_args = {
            "producer_service": args.producer_service,
            "consumer_service": args.consumer_service,
            "bus": args.bus,
        }
        print(
            json.dumps(
                kafka_topics(load_graph(Path(args.graph)), {k: v for k, v in filter_args.items() if v}),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "coverage-report":
        print(json.dumps(coverage_report(load_graph(Path(args.graph)), args.threshold), indent=2, sort_keys=True))
        return 0

    if args.command == "search":
        print(
            json.dumps(
                search(
                    load_graph(Path(args.graph)),
                    args.query,
                    fallback=args.fallback == "true",
                    limit=args.limit,
                    label=args.label,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "lens":
        lens_graph = load_graph(Path(args.graph))
        layers = layer_dirs(Path(args.workspace) if args.workspace else None, [Path(item) for item in args.layer_dir])
        dirs = lens_dirs(layers)
        if args.lenses_dir:
            dirs.append(Path(args.lenses_dir))
        specs = load_lens_specs(
            workspace=Path(args.workspace) if args.workspace else None,
            lenses_dir=dirs,
        )
        if args.action == "list":
            print(json.dumps(list_lenses(lens_graph, specs), indent=2, sort_keys=True))
            return 0
        if not args.name:
            raise SystemExit("lens requires --name unless using `cartograph lens list`")
        print(json.dumps(lens(lens_graph, args.name, specs, params=json.loads(args.params)), indent=2, sort_keys=True))
        return 0

    if args.command == "cgc-tool":
        print(
            json.dumps(
                cgc_tool(load_graph(Path(args.graph)), args.tool, json.loads(args.params)), indent=2, sort_keys=True
            )
        )
        return 0

    if args.command == "serve":
        from .serve import main as serve_main

        return serve_main([args.graph])

    if args.command == "tools":
        print(json.dumps(tool_catalog(), indent=2, sort_keys=True))
        return 0

    return 2
