# Shared Context for the 5-Doc Cartograph Rewrite

All five docs must be internally consistent and read as one product. This file is the source of truth — every doc writer reads it first.

## Product one-liner

Cartograph is **AI-first knowledge-graph code intelligence for polyrepo systems**. It builds a federated graph across 10–20+ services that an agent can query to trace flows ("what happens when we issue a motor-vehicle permit"), find call sites, and reason about cross-service contracts with verifiable confidence.

Cartograph is the **anti-CAST**: CAST Imaging requires a multi-week architect-driven onboarding to produce static diagrams. Cartograph indexes a polyrepo in minutes and exposes the result as a queryable substrate for AI agents (MCP), engineers (CLI/API), and humans (web UI).

## The three layers (canonical)

All docs reference these by name:

**Layer 1 — Packs.** YAML rules + tree-sitter queries. Deterministic, fast, ~free at query time. Handles 70–90% of common framework code.

**Layer 2 — LLM extraction.** Two-stage pipeline: model extracts the semantic claim via structured-output schema, deterministic code re-locates the anchor by function-name + literal match. Two-pass consensus filters false positives. Handles the wild 10–30%. Cents per repo, results cached by `(content_hash, prompt_version, model_version)`.

**Layer 3 — Agents.** Query-time intelligence. Walks gaps in the substrate when a user asks a specific question. Highest cost, only triggered on demand.

Every node and edge in the graph carries a `source` property: `pack:<rule-id>` or `llm:<model>@<date>` or `agent:<tool-id>@<date>`. Confidence is `high` / `medium` / `low` per node, tied to the rule or model that produced it.

## Milestone map

| Milestone | Layer 1 | Layer 2 | Layer 3 | UI |
|---|---|---|---|---|
| M1 — Indexable | full | – | – | – |
| M1.5 — Wild-Code | full | full | – | – |
| M2 — Queryable | full | full | full | – |
| M3 — Visible | full | full | full | full |

## Decisions locked

1. **MCP design is option 3:** Cartograph-native tool design (polyrepo-aware, flow-first), plus a thin **CGC-compat shim** that exposes our graph through CodeGraphContext's 21-tool surface for users migrating from CGC.
2. **Polyrepo is M1 Day-1**, not deferred. Service-namespacing in the graph schema from the start.
3. **M1.5 is a standalone milestone**, not folded into M1. Pack-only baseline ships and is validated before the probabilistic layer is added.
4. **Test exclusion and producer dedup are default M1 engine behaviour**, not opt-in. They are the difference between 12.5% precision (Spike B baseline) and 100% precision on the same code.
5. **Don't fork CodeGraphContext.** Import their graph in M1 (`source: cgc-import`) and offer the compat shim in M2.
6. **No gRPC, no polyglot beyond Java/JS/TS/Python in M1.** Flagship M2 add-on.

## Spike findings (citable across docs)

**Spike A — Polyrepo federation (validated):** On a 3-service synthetic CityPermits split, the federation pattern (per-repo extract → namespace → merge → cross-repo linkers) produced 92 nodes / 25 edges with 8 cross-repo HTTP edges and 3 Kafka delivery edges. The motor-vehicle anchor trace spanned all 3 services correctly. Verdict: graph schema and lens model are sound. Findings: `spike/polyrepo/SPIKE-A-FINDINGS.md`.

**Spike B — Real-repo calibration (mixed):** On `piomin/sample-spring-kafka-microservices`, first run was **12.5% precision** because tests were scanned as production and producer nodes fanned out. After adding test-exclusion and producer dedup defaults, scored **100% precision and 100% recall**. On `spring-petclinic/spring-petclinic-microservices`, scored **0% recall** — WebClient and Eureka resolution are not in the pack set. On `GoogleCloudPlatform/microservices-demo` (polyglot gRPC), confirmed out of scope. Findings: `spike/real-repos/SPIKE-B-FINDINGS.md`.

**Spike C — LLM-assisted extraction (validated):** On the exact petclinic files where M1 scored 0%, two-pass LLM extraction with structured-output schema scored **5/5 (100%) precision and recall**, including the wild `discoveryClient.getInstances("customers-service")` case where no static rule could resolve the host. Line numbers drift 5–13 lines between passes and sometimes land in unrelated methods — so the architecture is **LLM extracts the claim, deterministic post-processor re-locates the anchor by function-name match**. Cost: ~$0.00015 per small Java file; 20-service polyrepo full re-index ≈ $1.20. Findings: `spike/real-repos/SPIKE-C-FINDINGS.md`.

## Adjacent OSS positioning

**CodeGraphContext** (Shashank Shekhar Singh, MIT, 3,268★, v0.4.9). 17 node labels, 7 relationships, 21 MCP tools, 20 tree-sitter languages, 5 DB backends (KuzuDB default). **Symbol-centric schema** (functions, classes, calls). Cartograph is **framework-centric** (endpoints, message handlers, flows). We import CGC graphs in M1 and offer compat in M2; we do not fork.

**Tree-sitter, KuzuDB, Sigma.js, MCP, LangGraph** are direct dependencies, not competitors.

**CAST Imaging v3** is the legacy competitor. Architect-driven, license-gated, no AI integration. Cartograph's value prop is the opposite stance on every axis.

## Style rules (binding on all 5 docs)

- Lead each section with the answer or key takeaway in the first line
- Short paragraphs, 2–3 sentences max, clear visual breaks between ideas
- **Bold** the 1–2 most important words per section so the reader's eye can find them when skimming
- Reserve bullet points for genuine lists of 3+ parallel items
- Skip preamble, throat-clearing, recaps of what the section already said
- No emojis. No exclamation points. Never use the words "scrape" / "scraping"
- Terse technical prose. Aim for engineering-leadership reader, not marketing.

## Document tone

These are PRDs + SDDs hybridised — they specify what gets built and why, with enough technical depth that an engineer can start the next day. Not strategy docs in the McKinsey sense.

Each doc opens with:
1. **One-line summary** of what this milestone delivers
2. **Why it ships now** (dependencies, prior validation)
3. **Body sections** specific to the doc

Each doc closes with:
1. **Out of scope** (what's deliberately deferred and to which later milestone)
2. **Success metrics** (concrete, measurable)
3. **Open questions** (no more than 3, named with owners if known)

## Cross-document references

Use relative-style links: `[M2 flow lens spec](./m2-queryable.md#flow-lens)`. Always reference the canonical layer names. Always cite spike findings by file path when claims are non-obvious.
