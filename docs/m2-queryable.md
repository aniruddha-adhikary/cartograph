# M2 — Queryable

## 1. One-line summary

M2 adds Layer 3 to the stack in the Graphify-style shape: a CLI-first query surface, an optional JSON-lines tool bridge for agents, a flow lens generator with three validated modes, deterministic semantic fallback for substrate gaps, structured flow explanations, and a CGC-compat adapter for teams migrating from CodeGraphContext.

---

## 2. Why M2 ships now

**M1 and M1.5 together produce a graph that is worth querying.** M1 (Indexable) delivered a polyrepo-aware substrate with service-namespaced nodes, cross-repo HTTP and Kafka edges, and the two cross-repo linker passes (`link-http-via-service-registry`, `link-kafka-by-topic`) that give the graph spatial coherence across repos. M1.5 (Wild-Code) layered the LLM extraction pipeline on top, closing the 0% recall gap on WebClient and Eureka patterns that pack rules could not reach, at roughly $1.20 per full 20-service re-index.

The result is a federated graph with enough coverage to answer real polyrepo questions. Spike A validated the flow lens model on a 3-service CityPermits split: 92 nodes, 25 edges, 8 cross-repo HTTP edges, 3 Kafka delivery edges, all resolved with `confidence: high`. The motor-vehicle anchor trace — the question that motivates the whole product — returned a closed 10-node / 6-edge subgraph spanning all three services correctly (`spike/polyrepo/SPIKE-A-FINDINGS.md`). A graph that can answer that question is ready to be queried.

---

## 3. CLI-first Agent Design

**The Graphify-style CLI is the primary contract for now.** Agents should invoke Cartograph as a local command-line tool, read JSON responses, and only fall back to raw source search after the graph narrows the target. This keeps setup trivial for Codex/Claude-style coding agents and avoids committing to MCP transport, KuzuDB, or Neo4j before the query semantics are stable.

`cartograph serve` remains available as a JSON-lines bridge with `tools/list` and `tools/call` for agents that prefer a long-running process. It exposes the same tool names and delegates to the same query functions. A full MCP package/transport can wrap this later without changing the graph query layer.

Each tool is polyrepo-aware by default: node IDs are service-namespaced, and multi-service results carry `from_service` / `to_service` annotations on edges. Agents discover commands with:

```bash
cartograph tools
```

**Tool surface:**

- `cartograph flow --graph <graph> --anchor <anchor>` — Return the closed flow subgraph anchored on an endpoint or symbol ID.
- `cartograph find-callers --graph <graph> --symbol <symbol>` — Return all nodes that call or emit to the given symbol or topic.
- `cartograph find-callees --graph <graph> --symbol <symbol>` — Return all nodes called or consumed by the given symbol.
- `cartograph endpoints-in-service --graph <graph> --service <service>` — List Endpoint nodes in the named service.
- `cartograph cross-service-edges --graph <graph> [--from-service <service>] [--to-service <service>]` — Return cross-service HTTP and message edges.
- `cartograph kafka-topics --graph <graph> [--consumer-service <service>]` — List message producers and consumers grouped by topic name.
- `cartograph coverage-report --graph <graph>` — Return per-service node counts and source/confidence breakdown.
- `cartograph search --graph <graph> --query <query>` — Exact-match substrate lookup by symbol name, path fragment, or topic name, with low-confidence fallback.
- `cartograph explain --graph <graph> --anchor <anchor>` — Produce a structured deterministic narrative of the flow subgraph.
- `cartograph lens --graph <graph> --name <lens> [--params <json>]` — Evaluate a generated lens or raw Kuzu Cypher project lens.
- `cartograph lens list --graph <graph>` — List generated and configured lenses with their return signatures.

All graph-returning CLI tools return JSON with a `confidence_summary` field: counts of `high`, `medium`, and `low` confidence nodes/edges in the result. Tools that trigger the fallback annotate affected nodes with `confidence: low` and `source: embedding-similarity`.

**Response shape** for graph-returning tools:

```json
{
  "name": "flow:permits-api::POST /api/permits/motor-vehicle",
  "nodes": [...],
  "edges": [...],
  "services_touched": ["web", "permits-api", "inspections-api"],
  "confidence_summary": {"high": 8, "medium": 2, "low": 0},
  "stats": {"n_nodes": 10, "n_edges": 6, "n_cross_repo_http": 1, "n_kafka_deliveries": 3}
}
```

The JSON-lines server is a thin wrapper over the graph query layer. It does not own business logic; it translates `tools/call` requests into the same Python query functions used by the CLI and returns typed JSON. A full MCP adapter is a later integration layer, not the M2 core.

---

## 4. Flow lens generator

The flow lens generator produces closed subgraphs that span service boundaries. It ships with three modes. All three produce the same output shape (`name`, `mode`, `anchors`, `nodes`, `edges`, `services_touched`, `stats`) so MCP callers do not need to branch on mode.

### Hand-anchored mode

**This is the killer query.** Given an anchor — an endpoint ID, a Kafka topic name, or any other node ID in the substrate — the generator walks forward via `HANDLES`, `CROSSES_TIER`, `KAFKA_DELIVERS`, and `HANDLES_KAFKA` edges, pulling in inbound `CROSSES_TIER` callers on the first pass so the lens starts at the user-facing entry point. A second pass surfaces `KafkaProducer` nodes co-located in the same service as any visited `Endpoint` or `KafkaConsumer`, capturing the handler-emits-event pattern where no explicit `EMITS` edge exists. Two iterations drain the async consumer chain.

Validated on the motor-vehicle trace (`spike/out/citypermits-motorvehicle-flow.json`): anchoring on `permits-api::POST /api/permits/motor-vehicle` returns **10 nodes / 6 edges spanning all 3 services**, with **1 cross-repo HTTP edge** (web → permits-api) and **3 Kafka deliveries** (permit.approved → inspections-api consumer → inspection.completed|cancelled → permits-api consumer). The trace reads end-to-end without any manual edge annotation. This is what `cartograph.flow(anchor)` calls at runtime.

The reference implementation is `spike/polyrepo/flow_lens.py:anchored_flow`. The production version adds: (a) an explicit `EMITS` edge pass using the LLM extraction results from M1.5, replacing the heuristic producer-surfacing step; (b) a configurable `depth` parameter (default 8 hops) to prevent runaway traversal in dense graphs; (c) `confidence: low` tagging for any node reached via the embedding fallback rather than graph traversal.

### Route-pattern clustering mode

**The default for bulk exploration.** Groups all `Endpoint` nodes by their `/api/<group>` URL prefix. Each cluster becomes one flow lens, anchored on the cluster's shortest-path endpoint, then augmented with all other endpoints in the cluster plus their inbound callers. This mode answers "show me everything under `/api/permits`" without requiring the caller to know specific endpoint IDs.

Validated in Spike A: 4 flows produced from the 3-service CityPermits graph (`spike/out/citypermits-flows.json`), each correctly covering the cross-tier callers for that API group. This mode is the basis for `cartograph.lens(name)` when the lens is auto-generated rather than hand-defined.

### Runtime-trace import mode

**Fills structural gaps with runtime evidence.** Accepts an OpenTelemetry trace (OTLP JSON export) and maps spans to graph nodes by service name and HTTP path or Kafka topic. Where a span target matches an existing substrate node, the edge is upgraded to `source: otel-trace@<timestamp>`. Where no substrate node exists for a span target, the importer creates a stub node with `confidence: low` and `source: otel-trace`. The result is merged into the federated graph and is available immediately to all query tools.

This mode is the read-side analog of M1.5's LLM extraction: it covers paths that neither packs nor LLM rules found, using runtime evidence as the signal. Trace import is a one-shot CLI command (`cartograph import-trace --otlp path/to/trace.json`) and does not require a running agent.

---

## 5. Domain and pattern lenses

**Lenses are named projections** over the substrate graph. In the CLI-first M2 implementation they are returned as graph-shaped JSON. Generated route and domain lenses are persisted as `Lens` nodes with `CONTAINS` edges during indexing. Authored project lenses are raw Kuzu Cypher query specs under `.cartograph/lenses/*.json`, so agents can add project-specific interpretation without changing Cartograph core.

**Pattern lenses** are fully deterministic. They are defined by node-label predicates and carry `confidence: high` unconditionally. The production set:

- `pattern.endpoints` — all `Endpoint` nodes across all services
- `pattern.controllers` — all `@RestController` / equivalent handler nodes
- `pattern.cross_tier_calls` — all `HttpCall` and `CROSSES_TIER` edge pairs
- `pattern.kafka_bus` — all `KafkaProducer`, `KafkaConsumer`, and `KAFKA_DELIVERS` edges
- `pattern.components` — all frontend `Component` nodes

The lens spike found these lenses are immediately production-quality with zero tuning: 100% precision on 119-node CityPermits substrate.

**Domain lenses** cluster nodes by deterministic token proximity in M2. This keeps the CLI dependency-free. A later LLM label-generation pass can improve names once the storage and cache layer exists.

The lens spike's recommendation stands: `CROSSES_TIER` edges only for cluster merging, not `HANDLES` edges. `HANDLES` edges pull a controller's own endpoints into the same cluster (already correct); `CROSSES_TIER` edges are the meaningful merging signal for cross-layer domain boundaries.

Domain lenses are persisted in the current graph JSON and fall back to deterministic generation if an older graph does not contain `Lens` nodes. The response carries `graph_version`, so callers can cache lens results externally.

**Configured lenses** use `kind: "query"` and `language: "kuzu-cypher"`. This avoids a Cartograph-specific mini-language: higher abstraction is expressed with normal graph patterns, shared variables, predicates, and projected bindings.

```json
{
  "project.struts-order-db-flow": {
    "kind": "query",
    "language": "kuzu-cypher",
    "returns": {
      "route": "Endpoint",
      "action": "StrutsAction",
      "query": "SqlQuery",
      "table": "DbTable"
    },
    "query": [
      "MATCH (route:Endpoint)-[dispatch:DISPATCHES_TO]->(action:StrutsAction)",
      "OPTIONAL MATCH (action:StrutsAction)-[uses:USES_QUERY]->(query:SqlQuery)",
      "OPTIONAL MATCH (query:SqlQuery)-[touches:TOUCHES_TABLE]->(table:DbTable)",
      "WHERE route.path CONTAINS 'order'",
      "RETURN route, dispatch, action, uses, query, touches, table"
    ]
  }
}
```

The checked-in CLI evaluator intentionally supports only the Kuzu Cypher subset needed by current fixtures. The spec is shaped this way so the later KuzuDB storage adapter can execute the same query text directly against Kuzu's typed property graph.

---

## 6. Semantic retrieval fallback

**The wild-query escape valve.** When an exact-match substrate query — by symbol name, path, or topic string — returns zero results, the search tool automatically falls back to deterministic token similarity over node text (`id`, `label`, and string properties). This is intentionally dependency-free in the CLI-first implementation.

All nodes returned via the fallback are tagged `confidence: low` and `source: embedding-similarity`. They appear in the same result structure as exact-match nodes, not in a separate list, so callers do not need to handle a different response shape. The `confidence_summary` field makes the fallback visible: a result with `{"high": 0, "medium": 0, "low": 5}` signals the caller that nothing reliable was found and the results are best-effort.

This is the read-side counterpart to M1.5's probabilistic extraction layer. M1.5 handles write-time gaps (code patterns pack rules miss); the fallback handles query-time gaps (queries for things not yet in the substrate). Both surfaces use `confidence: low` as the shared vocabulary.

**Implementation notes:** The CLI-first fallback is deterministic token similarity. Embedding-backed ranking can be added later behind the same `cartograph search` command without changing the response shape.

The fallback is opt-out, not opt-in. `cartograph.search(query, fallback: false)` disables it for callers that want strict exact-match behaviour.

---

## 7. Query-time agent for narrative flow explanations

**Layer 3 is only triggered by `cartograph explain`.** All other tools are deterministic graph queries. In CLI-first M2, explanation is deterministic structured narration over the flow subgraph. A pluggable LLM explainer can be layered in later behind the same command.

The agent receives:

- The flow subgraph (nodes + edges + `services_touched`)
- Node metadata: service name, label, path or topic, confidence tier, source rule
- The anchor (entry point the user asked about)

It produces a structured response:

```json
{
  "anchor": "POST /api/permits/motor-vehicle",
  "summary": "...",
  "steps": [
    {"hop": 1, "service": "web", "node": "HttpCall(/api/permits/motor-vehicle)", "description": "..."},
    ...
  ],
  "async_loops": ["permit.approved → inspections-api → inspection.completed → permits-api"],
  "confidence_notes": ["2 nodes are medium-confidence (Spring RestTemplate path resolution)"]
}
```

**Cost control** remains the design constraint for any future LLM explainer: no model is triggered by `cartograph flow` or any other query command. The current implementation has no model call and does not write to the graph.

---

## 8. CGC-compat shim

**A thin adapter, not a reimplementation.** CodeGraphContext exposes 21 MCP tools over a symbol-centric schema (functions, classes, calls, 17 node labels). The CGC-compat shim maps those 21 tools onto Cartograph graph queries where the schemas overlap, and returns a clear error message where they do not.

The shim is exposed through `cartograph cgc-tool` and the JSON-lines server. A separate `/mcp/cgc` endpoint is deferred with the full MCP adapter.

**Mapping strategy:**

Tools that map cleanly to Cartograph queries (these are implemented):

- `cgc.get_symbol_definition(symbol)` → `cartograph cgc-tool --tool cgc.get_symbol_definition --params '{"symbol":"..."}'`
- `cgc.find_references(symbol)` → `cartograph find-callers --symbol <symbol>`
- `cgc.get_callees(symbol)` → `cartograph find-callees --symbol <symbol>`
- `cgc.get_file_symbols(file_path)` → `cartograph cgc-tool --tool cgc.get_file_symbols --params '{"file_path":"..."}'`
- `cgc.get_dependencies(symbol)` → `cartograph flow --anchor <symbol> --depth 2`

Tools where schemas diverge (these return a structured error):

- `cgc.get_class_hierarchy(class)` — Cartograph's graph is framework-endpoint-centric, not class-hierarchy-centric. Error response: `{"error": "not_supported", "cartograph_equivalent": "cartograph.search(query) with label filter 'Component'", "reason": "Cartograph does not index class inheritance chains in M2; planned for M3 enterprise."}`
- `cgc.get_all_functions()` — No equivalent; Cartograph indexes endpoints and message handlers, not all functions. Error response directs caller to `cartograph.endpoints_in_service`.
- Any tool that writes to or modifies the CGC graph — Cartograph's graph is read-only via MCP in M2.

The shim is maintained as a compatibility aid, not a feature investment. It exists so migrating teams can do a two-step move: (1) point the CGC tool address at Cartograph's `/mcp/cgc` endpoint and verify the tools they actually use still work; (2) migrate callers to the Cartograph-native tool surface at their own pace.

No CGC source code is forked or vendored. The shim imports Cartograph's query layer directly.

---

## 9. Storage and versioning

**Graph JSON is the M2 storage contract.** The CLI-first implementation reads and writes graph JSON files. This keeps agent integration simple and keeps the query semantics independent of a database choice.

KuzuDB is the target graph query backend. The CLI JSON evaluator remains as the dependency-free harness for M2, but authored lenses use Kuzu Cypher text so the storage adapter can swap in Kuzu execution without changing project lens specs.

**Graph versioning** uses content-hash snapshots. Each full re-index produces a graph version identified by `sha256(sorted(node_ids + edge_keys))`. The version hash is stored alongside the graph and returned in every MCP tool response as `graph_version`. Clients can cache results keyed on `(query_params, graph_version)` and invalidate when the version changes.

Incremental transactional deltas and vector columns are deferred until a database adapter exists.

---

## 10. Out of scope

**UI rendering is M3.** The flow subgraph JSON returned by `cartograph.flow` is designed to be renderable as a swimlane diagram with services as lanes and Kafka topics as labelled async edges, but the renderer ships in M3. M2 produces the data; M3 makes it visible.

**Full graph editing is M3 enterprise.** M2's graph is read-only via MCP. Writing nodes or edges — for example, manually annotating a flow or overriding a confidence tier — requires the graph editing surface planned for M3 enterprise tier.

**gRPC and polyglot beyond Java/JS/TS/Python** are M2 add-ons (post-GA), not launch blockers. The Spike B finding that `GoogleCloudPlatform/microservices-demo` is out of scope for M1 applies equally to M2's index layer. The flow lens generator works on whatever the substrate contains; it does not add language support.

**Class hierarchy and full symbol graph** are not in M2. The CGC-compat shim's error messages for class-hierarchy tools are the explicit acknowledgement of this boundary.

---

## 11. Success metrics

M2 is complete when **five reference questions** can each be answered correctly with a verifiable JSON result returned by a CLI command or JSON-lines `tools/call`, with no manual post-processing:

1. **Motor-vehicle permit flow:** "When a motor-vehicle permit is issued, which services are involved and what async events does it trigger?" — `cartograph flow --anchor "/api/permits/motor-vehicle"` must return a subgraph covering all 3 services, 1 cross-repo HTTP edge, and 3 Kafka deliveries. Verified against `spike/out/citypermits-motorvehicle-flow.json`.

2. **Cross-service calls from web frontend:** "Show all cross-service calls originating from web-frontend." — `cartograph cross-service-edges --from-service web` must return all 5 outbound HTTP calls found in Spike A with no false positives.

3. **Kafka topics into inspections-api:** "Which Kafka topics flow into inspections-api?" — `cartograph kafka-topics --consumer-service inspections-api` must return the `permit.approved` topic with the correct producer (permits-api) and confidence tier (high).

4. **Endpoint discovery across services:** "Find all endpoints under /api/permits across services." — `cartograph endpoints-in-service --service permits-api --path /api/permits`, or `cartograph search --query /api/permits`, must return all permits-api endpoints without cross-contaminating inspections-api endpoints.

5. **Coverage reporting:** "Which services have coverage below 80% (ratio of LLM-extracted nodes to total nodes)?" — `cartograph coverage-report` must return a per-service breakdown distinguishing `source: pack:*` from `source: llm:*` nodes, with the low-coverage services correctly identified as those where WebClient or Eureka resolution was required (validated against Spike C findings).

Each answer is verified by a deterministic test: the returned subgraph is diffed against a known-good reference JSON. The test passes if node IDs and edge keys match exactly; node property values may differ as long as `confidence` tiers are correct.

---

## 12. Open questions

**Q1 — Embedding model selection (owner: infra lead).** The current CLI fallback is deterministic token similarity. If a later provider adds embeddings behind `cartograph search`, the choice between a general-purpose model and a code-specific model affects retrieval quality and cost. A short offline eval on the CityPermits substrate should resolve that before enabling embeddings by default.

**Q2 — CGC shim scope vs. maintenance cost (owner: PM).** The current shim plan implements 5 of CGC's 21 tools and errors on the rest. Some teams may rely on the unmapped tools. Before M2 ships, we need a decision on whether to extend the shim to the full 21-tool surface or to document the gap explicitly and accept that some CGC users will need to migrate rather than just re-point their tool address.

**Q3 — Storage adapter timing (owner: backend lead).** Graph JSON is enough for CLI-first M2. KuzuDB should be introduced after the CLI contract and golden command outputs stabilize; authored lens specs already use Kuzu Cypher to avoid a later migration.
