# Cartograph Strategy

---

## 1. Product one-liner and thesis

**Cartograph is AI-first knowledge-graph code intelligence for polyrepo systems.**

The thesis in one sentence: the primary unsolved problem in multi-service codebases is not symbol lookup — it is flow tracing across service boundaries, and that problem is not solvable with deterministic rules alone.

CAST Imaging proved there is enterprise demand for cross-service intelligence, then priced itself out of reach with architect-driven onboarding, static diagrams, and no AI integration. GitHub Copilot and its siblings proved LLMs can reason over code, but they reason over files, not graphs. Cartograph occupies the gap: a federated, queryable graph that an agent can walk at inference time.

The bet is that **framework-centric graph schemas** — endpoints, message handlers, flows, contracts — are more useful to a reasoning agent than symbol-centric schemas (functions, classes, call edges), and that the right architecture pairs fast deterministic rules with a cheap LLM escape valve for the frameworks those rules cannot reach.

---

## 2. The three layers

### Layer 1 — Packs

**Packs are the foundation.** A Pack is a YAML ruleset plus tree-sitter queries targeting a specific framework pattern — Spring REST endpoints, Kafka producers, Express routes. They are deterministic, run in milliseconds, and cost nothing at query time. Spike B (`spike/real-repos/SPIKE-B-FINDINGS.md`) showed that Packs alone, with test-exclusion and producer-dedup enabled by default, achieve 100% precision and 100% recall on `piomin/sample-spring-kafka-microservices`. The same spike showed 0% recall on `spring-petclinic/spring-petclinic-microservices` because WebClient and Eureka resolution are not in the pack set — which is exactly the gap Layer 2 exists to fill. Packs handle 70–90% of common framework code; the remaining 10–30% is the wild that requires probabilistic extraction.

### Layer 2 — LLM extraction

**The LLM escape valve handles what no static rule can reach.** The pipeline is two-stage: a model extracts the semantic claim (endpoint path, target service, message topic) via a structured-output schema; a deterministic post-processor re-locates the anchor in the source file by function-name and literal match. Spike C (`spike/real-repos/SPIKE-C-FINDINGS.md`) validated this design on the exact petclinic files where M1 scored 0% — two-pass consensus achieved 5/5 precision and recall, including the `discoveryClient.getInstances("customers-service")` case where no static rule could resolve the host. Line numbers drift 5–13 lines between LLM passes, which is why the post-processor, not the model, owns anchor placement. Cost is ~$0.00015 per small Java file; a 20-service polyrepo full re-index runs approximately $1.20. Results are cached by `(content_hash, prompt_version, model_version)` — the same content_hash used by the M1 pack cache, extended with prompt and model versions.

### Layer 3 — Agents

**Agents are query-time intelligence, not indexing infrastructure.** When a user asks "what happens when we issue a motor-vehicle permit," a Layer 3 agent walks gaps in the substrate — nodes and edges the static layers did not produce — to answer the specific question. This is the highest-cost layer and is only triggered on demand. It does not replace Layers 1 and 2; it extends them for questions the static graph cannot answer alone. Every node and edge in the graph carries a `source` property (`pack:<rule-id>`, `llm:<model>@<date>`, or `agent:<tool-id>@<date>`) and a `confidence` of `high`, `medium`, or `low`, so agents and users always know the epistemic status of a claim.

---

## 3. Milestone map

### M1 — Indexable

**M1 ships a deterministic, polyrepo-capable graph with no probabilistic layer.** A user points Cartograph at a set of repos, runs the indexer, and gets a federated graph: service-namespaced nodes, cross-repo HTTP edges, Kafka delivery edges, all sourced from Packs. Test exclusion and producer dedup are default engine behaviour, not opt-in — Spike B showed these two defaults are the difference between 12.5% precision and 100% precision on the same codebase. The MCP surface exposes Cartograph-native polyrepo-aware tools from day one, plus an optional CGC-compat shim (21-tool surface) for teams migrating from CodeGraphContext. Polyrepo is not deferred to a later milestone: service-namespacing is baked into the graph schema from the first commit.

### M1.5 — Wild-Code

**M1.5 adds the LLM extraction layer without changing the M1 interface contract.** Pack-only baseline ships and is validated in M1; M1.5 adds Layer 2 on top of a confirmed working foundation. This sequencing is deliberate — shipping a probabilistic layer before the deterministic baseline is calibrated produces unattributable failures. After M1.5, the graph covers the frameworks the pack set cannot reach (WebClient, Eureka-style service discovery, any framework where resolution requires dynamic string construction). The `source` and `confidence` fields introduced in M1 distinguish pack-derived edges from LLM-derived edges in every query result.

### M2 — Queryable

**M2 activates Layer 3 agents and the flow-lens query model.** Users can ask cross-service flow questions in natural language; an agent walks the substrate and returns a verified trace with per-edge provenance. M2 also ships the MCP CGC-compat shim as a first-class supported surface, and adds gRPC and polyglot support beyond Java/JS/TS/Python as the flagship M2 add-on (deferred from M1 by Decision 6). The agent design uses LangGraph; the graph backend is KuzuDB. M2 is the milestone at which Cartograph becomes a substrate for AI coding agents, not just a CLI tool for engineers.

### M3 — Visible

**M3 ships the web UI.** The graph is rendered with Sigma.js; users can navigate flows visually, inspect per-node confidence and source provenance, and drill into cross-service contracts. M3 does not change the underlying graph schema or query model — it is a rendering layer over the M2 substrate. The UI is explicitly last in the sequence because the graph must be correct and queryable before it is worth visualising. A beautiful diagram over a 12.5%-precision graph is the CAST failure mode.

---

## 4. Decisions locked

**1. MCP design is option 3: Cartograph-native tools plus a CGC-compat shim.**
The Cartograph MCP surface is polyrepo-aware and flow-first from day one. A thin shim exposes the same graph through CodeGraphContext's 21-tool surface for users migrating from CGC. The shim is additive — it does not constrain the native tool design. This avoids the CGC symbol-centric schema becoming a ceiling on what Cartograph can express.

**2. Polyrepo is M1 Day-1, not deferred.**
Service-namespacing is in the graph schema from the first commit. The federation pattern — per-repo extract, namespace, merge, cross-repo linkers — was validated in Spike A (`spike/polyrepo/SPIKE-A-FINDINGS.md`) on a 3-service CityPermits split: 92 nodes, 25 edges, 8 cross-repo HTTP edges, 3 Kafka delivery edges, correct motor-vehicle anchor trace spanning all 3 services. Deferring polyrepo would require a schema migration at exactly the wrong time.

**3. M1.5 is a standalone milestone, not folded into M1.**
The probabilistic layer introduces a new failure mode (false positives from LLM extraction) that the deterministic layer does not have. Validating the pack-only baseline before adding Layer 2 keeps failure modes attributable. If M1.5 were folded into M1, a precision regression could be caused by either layer and the debug surface doubles.

**4. Test exclusion and producer dedup are default M1 engine behaviour.**
Spike B (`spike/real-repos/SPIKE-B-FINDINGS.md`) ran the same codebase with and without these defaults. Without them: 12.5% precision. With them: 100% precision and 100% recall. These are not power-user settings — they are the minimum viable correctness bar. Shipping them as opt-in would mean every new user hits the 12.5% baseline first.

**5. Don't fork CodeGraphContext.**
Import their graph in M1 (`source: cgc-import`) and offer the compat shim in M2. CGC has 3,268 stars, 20 tree-sitter language parsers, and 5 database backends — these are features we get for free by treating CGC as an upstream rather than a competitor. Forking would create a maintenance surface with no user-facing benefit.

**6. No gRPC, no polyglot beyond Java/JS/TS/Python in M1.**
Spike B confirmed that `GoogleCloudPlatform/microservices-demo` (polyglot gRPC) is out of scope for M1. The pack-authoring surface for gRPC and Go/Ruby/Rust requires a separate spike. Shipping M1 with an incomplete gRPC pack is worse than shipping without it — partial coverage produces silent false negatives. gRPC and extended polyglot are the M2 flagship add-on.

---

## 5. Adjacent OSS positioning

**CodeGraphContext is an upstream, not a competitor.**
CGC (Shashank Shekhar Singh, MIT, 3,268★, v0.4.9) is symbol-centric: 17 node labels, 7 relationships, 21 MCP tools targeting functions, classes, and call edges. Cartograph is **framework-centric**: the primary entities are endpoints, message handlers, flows, and cross-service contracts. CGC answers "what calls this function"; Cartograph answers "what happens when we issue a motor-vehicle permit." The schemas are complementary, not redundant, which is why importing CGC graphs in M1 (`source: cgc-import`) and offering a compat shim in M2 is the right stance.

**Tree-sitter, KuzuDB, Sigma.js, MCP, and LangGraph are direct dependencies.**
Tree-sitter provides the parse layer for Pack rules across 20+ languages. KuzuDB is the graph backend (CGC's default; we inherit this choice). Sigma.js is the M3 rendering layer. MCP is the agent-facing protocol. LangGraph is the Layer 3 agent orchestration framework. None of these are in competition with Cartograph; all of them reduce the build surface.

**CAST Imaging v3 is the legacy incumbent.**
Architect-driven onboarding, license-gated access, static diagram output, no AI integration. CAST's value proposition requires a multi-week engagement before any graph exists. Cartograph indexes a polyrepo in minutes. Every axis of CAST's design is the opposite of Cartograph's — this is not positioning language, it is a literal description of the architectural difference.

---

## 6. What's deliberately not on the roadmap

**gRPC and polyglot beyond Java/JS/TS/Python are not M1 scope.**
Spike B confirmed that polyglot gRPC repos are out of scope for the M1 pack set. Adding partial gRPC coverage would produce silent false negatives, which is worse than a clean scope boundary. gRPC ships in M2 as a fully validated pack, not as a best-effort M1 addition.

**The CAST-style architect workflow is not a target.**
Cartograph does not require a multi-week onboarding, does not produce static diagrams as a primary deliverable, and does not gate access behind a per-seat license review. The architect-driven consumption model is the problem Cartograph solves, not a workflow to support. Any feature that requires a human architect in the indexing loop is out of scope indefinitely.

**Live runtime instrumentation is not on the roadmap.**
Cartograph is a static analysis tool. It reasons about code as written, not about traffic as observed. OpenTelemetry and distributed tracing are complements — a user might cross-reference Cartograph's graph with a trace — but Cartograph does not ingest runtime data, does not require a running system to index, and does not make claims about production traffic patterns.

---

## 7. Bet structure

**What we're betting on:**

- **Framework-centric graph schemas** produce more actionable query results for AI agents than symbol-centric schemas (functions, classes, call edges). An agent that can ask "what services does the permit-issuance flow touch" is more useful than one that can only ask "what calls this function."
- **The two-layer deterministic + LLM architecture** is the right cost/accuracy tradeoff. Packs handle 70–90% at near-zero marginal cost; LLM extraction handles the remaining 10–30% at cents-per-repo pricing. Spike C (`spike/real-repos/SPIKE-C-FINDINGS.md`) validated 100% precision and recall on the wild cases at ~$1.20 per 20-service polyrepo re-index.
- **Polyrepo-first is a durable differentiator.** Most static analysis tools treat a monorepo or a single service as the unit of analysis. Cross-service flow tracing requires a federated graph schema that single-service tools cannot retrofit.
- **MCP as the agent-facing protocol** is the right bet for the current AI coding assistant ecosystem. The 21-tool CGC-compat shim reduces switching cost for teams already on CGC.

**What we're betting against:**

- **CAST-style architect workflow.** Requiring a human expert to drive the indexing process limits the addressable market to large enterprises with dedicated tooling budgets and excludes the engineering-led teams that are Cartograph's primary users.
- **Symbol-centric graph schemas (CGC model) as the primary representation.** Functions and call edges are the right level of abstraction for a compiler or a linter, not for an agent trying to reason about cross-service contracts. A symbol graph does not know that `POST /permits` and the Kafka `permit.issued` topic are part of the same flow.
- **Framework-by-framework manual support without an LLM escape valve.** The M1 pack set cannot cover every framework. Any strategy that bets on eventually writing a Pack for every framework will always be behind. The LLM extraction layer is the structural answer to long-tail framework coverage — it handles the cases the pack set misses at cents-per-repo cost, without requiring a new pack author for every new framework pattern.

---

## 8. Open questions

**1. Pack authoring ownership model.**
Who writes and maintains Packs for frameworks outside the core Java/JS/TS/Python set — core team, community contributors, or framework vendors? The answer determines whether the pack registry is a controlled surface or an open ecosystem, and that choice affects the quality floor for `confidence: high` claims.

**2. LLM extraction cost floor at scale.**
Spike C cost estimates are based on small Java files in a 20-service polyrepo. The $1.20 per full re-index figure needs validation against a large monorepo-style service (100k+ LOC single service) before M1.5 pricing decisions are made. Cache hit rates in active repos with frequent commits are the key variable.

**3. CGC-compat shim scope.**
The CGC 21-tool surface exposes symbol-centric entities (functions, classes, calls) that do not map 1:1 onto Cartograph's framework-centric schema. The shim must either synthesise symbol nodes from framework nodes (lossy) or import a CGC graph directly (two-graph architecture). The right answer has implications for the M1 import design and should be resolved before M2 shim work begins.
