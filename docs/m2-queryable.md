# M2 — Queryable

## 1. One-line summary

M2 adds Layer 3 to the stack: a Cartograph-native MCP server, a flow lens generator with three validated modes, a semantic retrieval fallback for substrate gaps, a query-time agent for narrative explanations, and a CGC-compat shim for teams migrating from CodeGraphContext.

---

## 2. Why M2 ships now

**M1 and M1.5 together produce a graph that is worth querying.** M1 (Indexable) delivered a polyrepo-aware substrate with service-namespaced nodes, cross-repo HTTP and Kafka edges, and the two cross-repo linker passes (`link-http-via-service-registry`, `link-kafka-by-topic`) that give the graph spatial coherence across repos. M1.5 (Wild-Code) layered the LLM extraction pipeline on top, closing the 0% recall gap on WebClient and Eureka patterns that pack rules could not reach, at roughly $1.20 per full 20-service re-index.

The result is a federated graph with enough coverage to answer real polyrepo questions. Spike A validated the flow lens model on a 3-service CityPermits split: 92 nodes, 25 edges, 8 cross-repo HTTP edges, 3 Kafka delivery edges, all resolved with `confidence: high`. The motor-vehicle anchor trace — the question that motivates the whole product — returned a closed 10-node / 6-edge subgraph spanning all three services correctly (`spike/polyrepo/SPIKE-A-FINDINGS.md`). A graph that can answer that question is ready to be queried.

---

## 3. Cartograph-native MCP design

**Option 3 is the right design.** The decision locked in SHARED-CONTEXT.md rules out forking CodeGraphContext and rules out a thin shim as the primary surface. Cartograph's graph is framework-centric and polyrepo-aware; a symbol-centric CGC tool surface would require constant translation and would hide the product's differentiated capability — flow tracing across services.

The MCP server exposes 10 tools. Each tool is polyrepo-aware by default: node IDs are service-namespaced (`permits-api::POST /api/permits/motor-vehicle`), and multi-service results carry `from_service` / `to_service` annotations on edges.

**Tool surface:**

- `cartograph.flow(anchor, depth?)` — Return the closed flow subgraph anchored on an endpoint or symbol ID, spanning all services reachable via CROSSES_TIER and KAFKA_DELIVERS edges. This is the primary entry point.
- `cartograph.find_callers(symbol)` — Return all nodes that call or emit to the given symbol or topic, across repos.
- `cartograph.find_callees(symbol)` — Return all nodes called or consumed by the given symbol, across repos.
- `cartograph.endpoints_in_service(service)` — List all Endpoint nodes in the named service, with HTTP method, path, and confidence tier.
- `cartograph.cross_service_edges(filter?)` — Return all CROSSES_TIER and KAFKA_DELIVERS edges in the graph, optionally filtered by source or target service.
- `cartograph.kafka_topics(filter?)` — List all KafkaProducer and KafkaConsumer nodes, grouped by topic name, with producer-to-consumer links where resolved.
- `cartograph.coverage_report()` — Return per-service node counts, pack-vs-LLM source breakdown, and the list of services where recall is estimated below threshold (used to surface M1.5 re-index candidates).
- `cartograph.search(query, fallback?)` — Exact-match substrate lookup by symbol name, path fragment, or topic name. When `fallback: true` (default), triggers semantic retrieval if the exact match returns empty.
- `cartograph.explain_flow(anchor)` — Invoke the query-time agent (Layer 3) to produce a prose narrative of the flow subgraph returned by `cartograph.flow`. Returns structured text, not raw graph JSON.
- `cartograph.lens(name)` — Return the nodes and edges belonging to a named domain or pattern lens (see §5).

All tools return a `confidence_summary` field: counts of `high`, `medium`, and `low` confidence nodes in the result. Tools that trigger the semantic fallback annotate affected nodes with `confidence: low` and `source: embedding-similarity`.

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

The MCP server is a thin HTTP wrapper over the graph query layer. It does not own business logic; it translates tool calls into graph queries (Cypher for Neo4j, or KuzuDB's equivalent) and returns typed JSON. A single process, no sidecar, no message queue.

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

**Lenses are persistent named projections** over the substrate graph, stored as first-class nodes with `CONTAINS` edges to their member nodes. They do not duplicate data; they group it. Two lens families are carried forward from the lens spike (`spike/lenses/SPIKE-FINDINGS.md`).

**Pattern lenses** are fully deterministic. They are defined by node-label predicates and carry `confidence: high` unconditionally. The production set:

- `pattern.endpoints` — all `Endpoint` nodes across all services
- `pattern.controllers` — all `@RestController` / equivalent handler nodes
- `pattern.cross_tier_calls` — all `HttpCall` and `CROSSES_TIER` edge pairs
- `pattern.kafka_bus` — all `KafkaProducer`, `KafkaConsumer`, and `KAFKA_DELIVERS` edges
- `pattern.components` — all frontend `Component` nodes

The lens spike found these lenses are immediately production-quality with zero tuning: 100% precision on 119-node CityPermits substrate.

**Domain lenses** cluster nodes by semantic proximity. In M2, domain lens generation uses a two-step process: TF-IDF token clustering to produce initial groups, then a single LLM label-generation call per cluster (input: member node names + handler names, output: 1–3 word domain concept name). This replaces the dominant-token heuristic that the spike found accurate only ~60% of the time on multi-controller domains.

The lens spike's recommendation stands: `CROSSES_TIER` edges only for cluster merging, not `HANDLES` edges. `HANDLES` edges pull a controller's own endpoints into the same cluster (already correct); `CROSSES_TIER` edges are the meaningful merging signal for cross-layer domain boundaries.

Domain lenses are versioned by content hash and regenerated when the substrate changes by more than a configurable threshold (default: 10% of member nodes modified in a re-index).

---

## 6. Semantic retrieval fallback

**The wild-query escape valve.** When an exact-match substrate query — by symbol name, path, or topic string — returns zero results, the search tool automatically falls back to embedding similarity. The fallback embeds the query string, runs cosine similarity over pre-computed node embeddings (one embedding per node, covering `id`, `label`, and all string properties), and returns the top-k candidates.

All nodes returned via the fallback are tagged `confidence: low` and `source: embedding-similarity`. They appear in the same result structure as exact-match nodes, not in a separate list, so callers do not need to handle a different response shape. The `confidence_summary` field makes the fallback visible: a result with `{"high": 0, "medium": 0, "low": 5}` signals the caller that nothing reliable was found and the results are best-effort.

This is the read-side counterpart to M1.5's probabilistic extraction layer. M1.5 handles write-time gaps (code patterns pack rules miss); the fallback handles query-time gaps (queries for things not yet in the substrate). Both surfaces use `confidence: low` as the shared vocabulary.

**Implementation notes:** Node embeddings are computed at index time by the same model used for M1.5 LLM extraction (or a cheaper embedding-only model if cost is a constraint). They are stored as a vector column in the same KuzuDB or Neo4j instance, avoiding a separate vector database. Embedding updates are triggered by the same `(content_hash, model_version)` cache key used for M1.5 results.

The fallback is opt-out, not opt-in. `cartograph.search(query, fallback: false)` disables it for callers that want strict exact-match behaviour.

---

## 7. Query-time agent for narrative flow explanations

**Layer 3 is only triggered by `cartograph.explain_flow`.** All other tools are deterministic graph queries. The agent is not a general-purpose code assistant; it has one job: given a flow subgraph produced by `cartograph.flow`, generate a plain-English narrative of what happens when that flow executes.

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

**Cost control** is the critical design constraint for Layer 3. The agent call is gated behind an explicit `explain_flow` invocation — no agent is triggered by `cartograph.flow` or any other tool. The subgraph passed to the agent is capped at 50 nodes by default; graphs larger than this are truncated to the most-traversed path before being sent. Results are cached by subgraph content hash so repeated queries on unchanged graphs do not re-invoke the model.

The agent uses the same model as M1.5 LLM extraction, governed by the `(model_version, prompt_version)` cache key. It does not write to the graph.

---

## 8. CGC-compat shim

**A thin adapter, not a reimplementation.** CodeGraphContext exposes 21 MCP tools over a symbol-centric schema (functions, classes, calls, 17 node labels). The CGC-compat shim maps those 21 tools onto Cartograph graph queries where the schemas overlap, and returns a clear error message where they do not.

The shim is registered as a separate MCP server endpoint (`/mcp/cgc`) so teams can point their existing CGC-wired agents at Cartograph without reconfiguring tool names.

**Mapping strategy:**

Tools that map cleanly to Cartograph queries (these are implemented):

- `cgc.get_symbol_definition(symbol)` → `MATCH (n) WHERE n.id CONTAINS $symbol RETURN n LIMIT 1`
- `cgc.find_references(symbol)` → `cartograph.find_callers(symbol)`
- `cgc.get_callees(symbol)` → `cartograph.find_callees(symbol)`
- `cgc.get_file_symbols(file_path)` → graph query for all nodes where `source_file = $file_path`
- `cgc.get_dependencies(symbol)` → subgraph walk from symbol node via HANDLES / CALLS edges, depth 2

Tools where schemas diverge (these return a structured error):

- `cgc.get_class_hierarchy(class)` — Cartograph's graph is framework-endpoint-centric, not class-hierarchy-centric. Error response: `{"error": "not_supported", "cartograph_equivalent": "cartograph.search(query) with label filter 'Component'", "reason": "Cartograph does not index class inheritance chains in M2; planned for M3 enterprise."}`
- `cgc.get_all_functions()` — No equivalent; Cartograph indexes endpoints and message handlers, not all functions. Error response directs caller to `cartograph.endpoints_in_service`.
- Any tool that writes to or modifies the CGC graph — Cartograph's graph is read-only via MCP in M2.

The shim is maintained as a compatibility aid, not a feature investment. It exists so migrating teams can do a two-step move: (1) point the CGC tool address at Cartograph's `/mcp/cgc` endpoint and verify the tools they actually use still work; (2) migrate callers to the Cartograph-native tool surface at their own pace.

No CGC source code is forked or vendored. The shim imports Cartograph's query layer directly.

---

## 9. Storage and versioning

**KuzuDB is the default; Neo4j is a supported alternative.** KuzuDB is already the default for CodeGraphContext and is embedded (no separate process), which keeps the M2 deployment footprint small. Neo4j supports Cypher natively and is the right choice for teams that already operate a Neo4j instance or need the full APOC library for graph algorithms.

The query layer abstracts over both via a thin adapter interface. The two operations that differ between backends — bulk upsert and vector similarity search — have backend-specific implementations behind the same API.

**Graph versioning** uses content-hash snapshots. Each full re-index produces a graph version identified by `sha256(sorted(node_ids + edge_keys))`. The version hash is stored alongside the graph and returned in every MCP tool response as `graph_version`. Clients can cache results keyed on `(query_params, graph_version)` and invalidate when the version changes.

Incremental updates (triggered by file changes, not full re-index) produce a delta object: `{added: [...], modified: [...], removed: [...]}` keyed by node ID. Deltas are applied transactionally. The graph version advances on every delta commit. Lens memberships are recomputed lazily on the next query that touches affected nodes, not eagerly on every delta.

Embedding vectors are stored as a typed column in the same graph database, not in a separate vector store. This keeps deployment simple and ensures vector data stays in sync with structural data automatically.

---

## 10. Out of scope

**UI rendering is M3.** The flow subgraph JSON returned by `cartograph.flow` is designed to be renderable as a swimlane diagram with services as lanes and Kafka topics as labelled async edges, but the renderer ships in M3. M2 produces the data; M3 makes it visible.

**Full graph editing is M3 enterprise.** M2's graph is read-only via MCP. Writing nodes or edges — for example, manually annotating a flow or overriding a confidence tier — requires the graph editing surface planned for M3 enterprise tier.

**gRPC and polyglot beyond Java/JS/TS/Python** are M2 add-ons (post-GA), not launch blockers. The Spike B finding that `GoogleCloudPlatform/microservices-demo` is out of scope for M1 applies equally to M2's index layer. The flow lens generator works on whatever the substrate contains; it does not add language support.

**Class hierarchy and full symbol graph** are not in M2. The CGC-compat shim's error messages for class-hierarchy tools are the explicit acknowledgement of this boundary.

---

## 11. Success metrics

M2 is complete when **five reference questions** can each be answered correctly with a verifiable subgraph returned by an MCP tool call, with no manual post-processing:

1. **Motor-vehicle permit flow:** "When a motor-vehicle permit is issued, which services are involved and what async events does it trigger?" — `cartograph.flow("permits-api::POST /api/permits/motor-vehicle")` must return a subgraph covering all 3 services, 1 cross-repo HTTP edge, and 3 Kafka deliveries. Verified against `spike/out/citypermits-motorvehicle-flow.json`.

2. **Cross-service calls from web frontend:** "Show all cross-service calls originating from web-frontend." — `cartograph.cross_service_edges(filter: {from_service: "web"})` must return all 5 outbound HTTP calls found in Spike A with no false positives.

3. **Kafka topics into inspections-api:** "Which Kafka topics flow into inspections-api?" — `cartograph.kafka_topics(filter: {consumer_service: "inspections-api"})` must return the `permit.approved` topic with the correct producer (permits-api) and confidence tier (high).

4. **Endpoint discovery across services:** "Find all endpoints under /api/permits across services." — `cartograph.endpoints_in_service` combined with a path filter, or `cartograph.search("/api/permits")`, must return all permits-api endpoints without cross-contaminating inspections-api endpoints.

5. **Coverage reporting:** "Which services have coverage below 80% (ratio of LLM-extracted nodes to total nodes)?" — `cartograph.coverage_report()` must return a per-service breakdown distinguishing `source: pack:*` from `source: llm:*` nodes, with the low-coverage services correctly identified as those where WebClient or Eureka resolution was required (validated against Spike C findings).

Each answer is verified by a deterministic test: the returned subgraph is diffed against a known-good reference JSON. The test passes if node IDs and edge keys match exactly; node property values may differ as long as `confidence` tiers are correct.

---

## 12. Open questions

**Q1 — Embedding model selection (owner: infra lead).** The semantic retrieval fallback and domain lens clustering both require node embeddings. The choice between a general-purpose model (e.g., `text-embedding-3-small`) and a code-specific model (e.g., `voyage-code-3`) affects both retrieval quality and cost. A short offline eval on the CityPermits substrate against the 5 reference questions above should resolve this before M2 GA.

**Q2 — CGC shim scope vs. maintenance cost (owner: PM).** The current shim plan implements 5 of CGC's 21 tools and errors on the rest. Some teams may rely on the unmapped tools. Before M2 ships, we need a decision on whether to extend the shim to the full 21-tool surface or to document the gap explicitly and accept that some CGC users will need to migrate rather than just re-point their tool address.

**Q3 — KuzuDB vector search readiness (owner: backend lead).** KuzuDB's vector similarity support is recent. If the embedded vector search is not production-ready for cosine similarity over 10k+ node embeddings at acceptable latency, the fallback will need to either (a) defer to a separate vector index (Chroma or similar, adding a deployment component) or (b) limit the fallback to BM25 over node string properties until KuzuDB matures. Needs a latency benchmark on the federated graph before shipping the fallback as a default-on feature.
