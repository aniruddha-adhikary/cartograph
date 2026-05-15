---
name: cartograph
description: "Use Cartograph whenever a task touches service boundaries, endpoints, HTTP/Feign/message-bus topology, cross-service flows, database access paths, or 'where should I edit?' questions in a polyrepo. Trigger this skill even when the user doesn't say 'graph' — phrases like 'what services call X', 'who publishes to topic Y', 'show me the flow for endpoint Z', 'which microservices does this depend on', or 'find all consumers of …' all mean Cartograph first, source grep second."
---

# Cartograph

Cartograph is a graph-first navigation layer for polyrepo codebases. It indexes services, endpoints, message handlers, HTTP calls, database queries, and cross-service contracts into a single graph, then lets you query that graph instead of doing wide source searches.

The why: in a polyrepo system, the answer to "what happens when /api/orders is hit?" lives in 5–10 files across 3–4 services. Grep finds occurrences. Cartograph traces the actual chain.

## When to reach for this skill

| User intent | Cartograph command |
|---|---|
| "Trace what happens when X runs" | `cartograph explain --anchor <X>` |
| "Show the flow through X" | `cartograph flow --anchor <X>` |
| "Who calls X / who consumes topic Y?" | `cartograph find-callers --symbol <X>` |
| "What does X call / produce?" | `cartograph find-callees --symbol <X>` |
| "Endpoints exposed by service S" | `cartograph endpoints-in-service --service <S>` |
| "Cross-service calls from S" | `cartograph cross-service-edges --from-service <S>` |
| "Which topics reach S?" | `cartograph kafka-topics --consumer-service <S>` |
| "Where should I edit?" (semantic) | `cartograph search --query <terms>` |
| "What lenses can I run?" | `cartograph lens list` |

Reach for source grep only after the graph fails or you need exact line edits.

## Default workflow

1. **Check for an existing graph.** If `cartograph-out/graph.json` exists, query it directly.
2. **Index if missing or stale.** Run `cartograph index --workspace . --out cartograph-out/graph.json`.
3. **Query before grepping.** Use the table above.
4. **Check what's missing.** Read `cartograph-out/graph.json` `meta.unresolved` — these are the gaps the linker couldn't close on its own.
5. **Run the refinement loop** if there are unresolved entries that matter to your task. See [references/refinement-loop.md](references/refinement-loop.md).
6. **Read source files** to verify before editing — the graph points you to the right files; the source is the source of truth.
7. **Re-index** after structural code changes (`cartograph index ...`).

## The graph model in one screen

Cartograph emits a small, stable set of node labels and edge types. Every node carries `service`, `source` (which lens produced it), and `confidence` (`high` | `medium` | `low`).

Common labels:
- `Service`, `Endpoint`, `HttpCall`, `Component`
- `KafkaProducer`, `KafkaConsumer`, `MessageProducer`, `MessageConsumer`
- `ConfigProperty`, `DatabaseQuery`, `Action`, `Servlet`
- `Lens` (persisted query results)

Common edge types:
- `CROSSES_TIER` — cross-service HTTP (HttpCall → Endpoint)
- `KAFKA_DELIVERS`, `MESSAGE_DELIVERS` — producer → consumer
- `HANDLES`, `HANDLES_KAFKA`, `HANDLES_MESSAGE` — service → handler
- `CONTAINS`, `EMITS` — structural

Schemas per label are stored in `graph.meta.schema` so you can introspect what fields exist.

## Three kinds of lenses

Cartograph's extraction and querying is entirely lens-driven — there is no hardcoded language logic. There are three lens scopes, each solving a different problem:

- **`scope: source`** — match files, emit nodes/edges. This is how endpoints, HTTP calls, message handlers, etc. get extracted. Strategies: `regex`, `annotation-method`, `token-line`, `xml-element`, `config-key`, `tree-sitter`.
- **`scope: resolve`** — match existing nodes by label/field, parse a captured value, set structured fields. Example: take a node with `url=http://customers-service/owners`, extract `host=customers-service` and `path=/owners` so the linker can match it.
- **`scope: graph`** — run a Cypher-style query against the indexed graph. Used for higher-level views ("all endpoints whose path matches `/api/permits/*`").

When the framework or pattern you need isn't covered, write a project lens in `.cartograph/lenses/*.json`. See [references/lens-authoring.md](references/lens-authoring.md) for the patterns.

## The refinement loop (this is the core idea)

Cartograph doesn't try to silently guess at things it can't resolve. When the linker can't connect an HttpCall to an endpoint or a producer to a consumer, it records a structured **unresolved** entry on `graph.meta.unresolved` describing exactly what it tried and what it couldn't find. The list is the contract between the tool and you (the agent).

Your job, when a query comes back thin or empty:

1. Run `cartograph index ...` and inspect `meta.unresolved`.
2. For each unresolved item, look at the `raw` field — the lens captured something (a URL, a Feign annotation, a host variable name). Read the source file at the cited line.
3. Resolve via one of three escalating mechanisms:
   - **`service-registry.yaml`** at the workspace root — maps hostnames/Feign-client-names to service names. Cheapest fix.
   - **A `resolve` lens** in `.cartograph/lenses/` — parses raw values into structured fields with a regex. Use when the pattern is general (e.g., all URLs need host/path split).
   - **`resolve-hints.json`** at the workspace root — node-by-node patches for cases too specific to express as a lens (e.g., "this gateway HttpCall with url=/orders targets ftgo-order-service because it's routed via a runtime-injected env var").
4. Re-index and re-query.

Full details and worked examples in [references/refinement-loop.md](references/refinement-loop.md).

## Output you can rely on

After indexing, the graph file contains:
- `meta.services` — every service Cartograph saw
- `meta.node_count`, `meta.edge_count`, `meta.lens_count`
- `meta.unresolved` — gaps to investigate (empty list = clean graph)
- `meta.resolve_hints_applied` — count of hint patches applied
- `nodes[]`, `edges[]` — the graph itself

Query commands print JSON to stdout. Pipe to `jq` for inspection or read with `json.loads` in Python.

## References

- [references/commands.md](references/commands.md) — full task-to-command mapping
- [references/lens-authoring.md](references/lens-authoring.md) — writing `source`, `resolve`, and `graph` lenses
- [references/refinement-loop.md](references/refinement-loop.md) — how to close graph gaps with `service-registry.yaml`, resolve lenses, and `resolve-hints.json`
- [references/project-layers.md](references/project-layers.md) — overlay precedence, project vs. team config
