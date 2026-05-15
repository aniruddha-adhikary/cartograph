# M1 — Indexable

## One-line summary

M1 ships a deterministic, polyrepo-aware **pack-only indexing substrate** — Layer 1 complete, Layers 2 and 3 deliberately absent — with enough real-world pack coverage (Spring REST + WebClient + Eureka, Express/Node, React, Kafka) to produce a graph that is honest, queryable by machines, and provably better than any prior baseline on the calibrated target repos.

---

## Why M1 ships now

**Spike A validated the federation architecture.** The per-repo extract → namespace → merge → cross-repo linker pattern produced 92 nodes / 25 edges across a 3-service polyrepo, with 8 cross-repo HTTP edges and 3 Kafka delivery edges all resolving to the correct downstream service. The motor-vehicle permit trace spanned all three services with no false paths. The graph schema needed no structural change beyond adding a `service` property to every node — the linker model is sound. Full findings: [`spike/polyrepo/SPIKE-A-FINDINGS.md`](../spike/polyrepo/SPIKE-A-FINDINGS.md).

**Spike B identified the exact defects to fix.** On `piomin/sample-spring-kafka-microservices`, the first unguarded run scored 12.5% precision because test sources were scanned as production code and producer nodes fanned out combinatorially. After adding test-path exclusion and producer dedup as default engine behaviour, the same repo scored 100% precision and 100% recall. On `spring-petclinic/spring-petclinic-microservices`, recall was 0% — not because the architecture was wrong, but because the `spring-webclient` and `spring-cloud-eureka` packs did not exist. Those two packs are concrete M1 deliverables. Full findings: [`spike/real-repos/SPIKE-B-FINDINGS.md`](../spike/real-repos/SPIKE-B-FINDINGS.md).

M1.5 (LLM extraction) is a separate milestone. The pack-only baseline ships and is calibrated first; the probabilistic layer is added only after M1 precision and recall targets are confirmed in production.

---

## Scope — what's in

M1 delivers:

- Graph schema v1 with canonical `service`, `source`, and `confidence` properties on every node and edge
- Pack engine with default test exclusion, producer dedup, project-level pack config overlays, and a forward-compatible file-hash caching scheme
- Spring pack family: REST controllers (`spring-rest-controller`), Kafka producer/consumer (`spring-kafka`, `spring-kafka-config`), WebClient (`spring-webclient`), Eureka service-name resolver (`spring-cloud-eureka`), RestTemplate (`spring-rest-template`)
- Express/Node pack family: route handlers (`express-routes`), kafkajs producer/consumer (`kafkajs`), axios and fetch HTTP calls (`js-fetch-hosted`)
- React pack: component extraction (`react-components`)
- Auto-author skill: `discover_frameworks.py` + `synthesize_pack.py` loop for frameworks outside the shipped set
- Polyrepo federation driver: per-repo extraction, service namespacing, merge, and three production linker passes (`link-http-via-service-registry`, `link-http-via-eureka`, `link-kafka-by-topic`)
- CGC importer: read a CodeGraphContext graph export and re-emit nodes with `source: cgc-import`
- Agent integration installer: writes Codex/Claude skill instructions and graph-first repo guidance modelled on Graphify's operational pattern
- Runtime view/plugin layer: built-in views such as `kafka-topics` are configuration, and project-specific graph queries can be added through `.cartograph/views/*.json` or explicit `.cartograph/plugins/*.py`

---

## Real-world calibration corpus

**M1 is gated by real Java systems, not toy fixtures.** The calibration set intentionally mixes monorepo-style multi-module projects, polyrepo-style checkouts, synchronous REST, service discovery, asynchronous Kafka, and legacy Java web stacks so the indexer is tested against the patterns that make cross-service reasoning hard.

| Corpus | Shape | Why it is in M1 | M1 evidence required |
|---|---|---|---|
| [`piomin/sample-spring-kafka-microservices`](https://github.com/piomin/sample-spring-kafka-microservices) | Java 21, Maven multi-module, 3 services: `order-service`, `payment-service`, `stock-service` | Validates Spring Kafka producers, consumers, config properties, default test exclusion, and producer dedup against a real Saga/Kafka example | Expected service-pair graph contains only the real Kafka deliveries between order, payment, and stock services; no `src/test/**` producers or consumers contribute edges |
| [`spring-petclinic/spring-petclinic-microservices`](https://github.com/spring-petclinic/spring-petclinic-microservices) | Spring Cloud microservices with API gateway, config server, discovery server, customers, vets, visits, and GenAI services | Validates REST endpoint extraction, WebClient call extraction, and Eureka service-name resolution across a larger Java system | Expected HTTP graph resolves gateway/client calls to `customers-service`, `vets-service`, and `visits-service` via `spring.application.name`, with `confidence: medium` on Eureka-derived edges |
| [`ewolff/microservice-kafka`](https://github.com/ewolff/microservice-kafka) | Java Spring Kafka sample with order, shipping, and invoicing services | Regression corpus for literal topic matching, separate consumer groups, and test-source isolation on a second Kafka codebase | Topic `order` links one producer service to two consumer services without counting embedded-Kafka tests as production consumers |
| [`apache/struts-examples`](https://github.com/apache/struts-examples) | Official Apache Struts2 multi-module examples, materialized as selected WAR-style services | Validates Struts action XML, servlet/J2EE descriptors, JSP-adjacent XML, and SQL mapper extraction without Spring assumptions | Expected graph includes `Action`, `Endpoint`, and `DatabaseQuery` nodes from selected modules such as `basic-struts`, `annotations`, `form-processing`, and `crud` |
| CityPermits split fixture | Synthetic but polyrepo-shaped: web, permits API, inspections API | Keeps the exact Spike A flow trace stable while real repos cover framework diversity | Motor-vehicle permit flow still spans all 3 services with 8 cross-repo HTTP edges and 3 Kafka deliveries |

**Large-scale means many repos in one federation.** The M1 CI job checks out each service directory as if it were an independently versioned repository, even when the upstream sample is published as a single GitHub repo. For `piomin` and `petclinic`, the harness materialises a workspace like:

```text
workspace/
  order-service/
  payment-service/
  stock-service/
  spring-petclinic-api-gateway/
  spring-petclinic-customers-service/
  spring-petclinic-vets-service/
  spring-petclinic-visits-service/
  spring-petclinic-config-server/
  spring-petclinic-discovery-server/
```

Each directory gets an explicit `cartograph.yaml` service name and is indexed independently before merge. This tests the same namespacing, collision handling, and linker code path a customer uses for a true 10-20 repo checkout.

**Scale pass/fail is structural, not anecdotal.** The large-workspace gate must index the combined Java corpus in a single run, produce service-namespaced IDs for every node, and emit a federation report with:

- zero duplicate node IDs after namespacing
- zero edges sourced from excluded test paths
- at least one resolved cross-service HTTP edge from Petclinic
- at least one resolved Kafka delivery in each Kafka corpus
- no `low` confidence edges unless they come from an auto-authored pack or CGC import
- no gRPC, Kubernetes, or runtime-trace nodes in the M1 graph

The purpose of the large-scale gate is not to prove every possible edge in these projects is recoverable by Layer 1. It proves the deterministic substrate can process real multi-service Java workspaces without false-positive fanout, namespace collisions, or scope drift.

---

## Graph schema

**Every node carries five canonical properties** regardless of label. Additional label-specific properties follow.

### Canonical node properties

| Property | Type | Description |
|---|---|---|
| `id` | string | Stable, globally unique. Format: `{service}:{file}:{byte_offset}` |
| `label` | string | One of the node labels listed below |
| `service` | string | Service name as declared in `service-registry.yaml` or inferred from repo root directory name |
| `source` | string | `pack:<rule-id>` for M1 nodes. Format: `pack:spring-webclient` |
| `confidence` | enum | `high` / `medium` / `low` — set by the rule that emitted the node |

### Node labels and label-specific properties

**`Service`** — a REST controller class or Express app root.
- `kind`: `rest-controller` | `express-app` | `express-router`
- `framework`: `spring` | `express`
- `name`: class or module name
- `file`, `line`

**`Endpoint`** — a single route handler (one HTTP method + path).
- `http_method`: `GET` | `POST` | `PUT` | `DELETE` | `PATCH`
- `path`: absolute path template, e.g. `/api/permits/{id}`
- `handler`: qualified method or function name
- `file`, `line`

**`HttpCall`** — an outbound HTTP call from client code.
- `http_method`
- `path`: path template extracted from the call site
- `host_var`: variable or literal host segment (used by the Eureka resolver)
- `file`, `line`

**`KafkaProducer`** — a call site that publishes to a Kafka topic.
- `topic`: resolved topic string or `{var}` if only a variable name was found
- `topic_var`: original variable name when `topic` is a `{var}` placeholder
- `file`, `line`

**`KafkaConsumer`** — a listener bound to one or more Kafka topics.
- `topics`: list of topic strings
- `group_id`: consumer group if statically determinable
- `file`, `line`

**`KafkaConsumerClass`** — the class that hosts one or more `KafkaConsumer` methods.
- `name`, `file`, `line`

**`ConfigProperty`** — a resolved Spring `@Value` or `application.yml` property.
- `key`: property key (e.g. `app.kafka.topic.permit-approved`)
- `default_value`: the `:default` fragment if present
- `file`, `line`

**`Component`** — a React component or an Express router module.
- `name`, `kind`: `react-component` | `express-router-module`
- `file`, `line`

**`RouterMount`** — an Express `app.use(prefix, router)` mount point.
- `prefix`: path prefix string
- `router_var`: variable name referencing the mounted router
- `file`, `line`

**`File`** — one source file. Emitted as the root node for every indexed file.
- `path`: repo-relative path
- `language`: tree-sitter language name

### Canonical edge properties

| Property | Type | Description |
|---|---|---|
| `type` | string | Edge type (see below) |
| `from` | string | Source node `id` |
| `to` | string | Target node `id` |
| `from_service` | string | `service` of the source node |
| `to_service` | string | `service` of the target node |
| `cross_repo` | bool | `true` when `from_service ≠ to_service` |
| `confidence` | enum | `high` / `medium` / `low` |

### Edge types

- `HANDLES` — Service → Endpoint (controller owns route)
- `CROSSES_TIER` — HttpCall → Endpoint (cross-tier HTTP resolution)
- `KAFKA_DELIVERS` — KafkaProducer → KafkaConsumer (resolved by topic name)
- `HANDLES_KAFKA` — KafkaConsumerClass → KafkaConsumer (class owns listener)
- `EXPOSES` — Endpoint outbound placeholder, rewritten by linkers
- `MOUNTS` — RouterMount → Component (Express module resolution)

---

## Pack engine

**The engine is deterministic and fast.** Each source file is parsed once with tree-sitter. Only rules whose `when.language` and `when.imports_any` gates match are applied. Sub-rules run scoped to the parent match, inheriting captured variables. No file is read twice.

### Rule evaluation order

1. Load bundled pack config from `cartograph/packs/*.json`, then merge project overlays from `.cartograph/packs/*.json` or `--packs-dir`. Validate schema on startup.
2. For each file in the repo (after exclusion filtering): match language, check `imports_any`, run matching rules, evaluate `where` constraints, expand `{capture | filter}` templates, emit nodes and edges to the in-memory graph.
3. Run linker passes in order: local path resolution, `link-http-via-service-registry`, `link-http-via-eureka`, `link-kafka-by-topic`.

### Project pack overlays

**Framework-specific names live in config, not extractor code.** The engine owns reusable extraction shapes: Java annotations, Java method-call literals, Spring Cloud Gateway route blocks, JavaScript route calls, and topic producer/consumer calls. The pack config supplies the framework vocabulary for those shapes.

Bundled config lives under `cartograph/packs/`. A project can override it without forking Cartograph:

```text
.cartograph/
  packs/
    spring.json
    javascript.json
```

The merge is deep and deterministic: a project overlay can add a controller annotation, HTTP client token, route predicate name, or named message-bus definition while inheriting the rest of the bundled pack. Lists append unique values by default, and named object lists such as `message_buses` merge by `name`. This is the M1-compatible landing zone for M1.5 discovery. The LLM may propose an overlay, but the M1 indexer only runs reviewed deterministic config.

### Runtime graph views

**Named graph queries are also configuration.** Built-in query names such as `kafka-topics`, `endpoints`, and `cross-service-edges` are bundled view specs in `cartograph/views/default.json`, not separate CLI branches. Projects can add or override views under `.cartograph/views/*.json` and run them with:

```bash
cartograph query --graph cartograph-out/graph.json --name <view-name> --workspace .
```

For logic that cannot be expressed as a declarative view, a project may add an explicit local plugin under `.cartograph/plugins/<name>.py` with a `run(graph, args)` function, then invoke it with `cartograph run-plugin --allow-plugin`. This is intentionally explicit: LLM-authored runtime behavior lives in the project, is reviewable in git, and is never smuggled into Cartograph core.

### Default exclusion patterns

The engine applies these exclusions before any rule runs. They are on by default; a per-repo `cartograph.yaml` can add project-specific patterns through `exclude:` / `excludes:` / `additional_excludes:`, but cannot remove the core set without an explicit `include_test_paths: true` flag.

- `src/test/**`
- `tests/`
- `__tests__/`
- `*Tests.java`
- `*.test.{js,ts,tsx}`
- `*.spec.{js,ts,tsx}`
- `node_modules/`
- `target/`
- `build/`
- `dist/`

The rationale is concrete: without these exclusions, `piomin/sample-spring-kafka-microservices` produces 16 KAFKA_DELIVERS edges at 12.5% precision. With them it produces 4 edges at 100% precision on the same codebase ([`spike/real-repos/SPIKE-B-FINDINGS.md`](../spike/real-repos/SPIKE-B-FINDINGS.md)).

### Producer dedup

After extraction and before any cross-repo linker pass, the engine runs a dedup pass over all producer-class nodes (KafkaProducer, HttpCall, and any future call-site node labels). The **dedup key is `(service, file, line, topic-or-topic-var)`**. Multiple AST-level captures that resolve to the same key are collapsed to a single node. This eliminates the combinatorial edge fanout that the Spike B first run exposed.

### File-hash caching

M1 is fully deterministic; caching is forward-compatible scaffolding for M1.5, not a functional requirement at this milestone.

**M1 cache key:** `(content_hash, pack_version)`

`content_hash` is the SHA-256 of the file's byte content. `pack_version` is the semver string from `pack.yaml`. A cached result is valid if both values match the stored entry. Invalidation is automatic on any file edit or pack update.

**M1.5 extension:** the key extends to `(content_hash, pack_version, prompt_version, model_version)` without changing the M1 key structure. LLM extraction results are cached against the same content hash, so a file that hasn't changed never re-invokes the model regardless of how many times the index is rebuilt. This key shape is the reason M1 does not use a simpler `file_path + mtime` key.

---

## Pack family shipped in M1

### Spring

**`spring-rest-controller`** — detects `@RestController` / `@Controller` classes and their `@{Get,Post,Put,Delete,Patch}Mapping` methods. Emits `Service` + `Endpoint` nodes. Resolves class-level `@RequestMapping` base paths to absolute endpoint paths. `confidence: high`.

**`spring-kafka`** — detects `KafkaTemplate.send(topic, ...)` producers and `@KafkaListener(topics = "...")` consumers. `confidence: high` for literal topic strings.

**`spring-kafka-config`** — detects `@Value("${app.kafka.topic.x:default}")` field injections. Emits `ConfigProperty` nodes that the Kafka linker uses to resolve topic variables at federation time. `confidence: high`.

**`spring-rest-template`** — detects `RestTemplate.{getForObject, postForEntity, exchange}` call sites. Emits `HttpCall` nodes. `confidence: high` for literal URLs; `medium` for binary-expression URL concatenation (walks the expression chain, concatenates literal segments, marks non-literal segments as `{param}`).

**`spring-webclient`** — detects the `WebClient` fluent builder pattern: `.uri("http://<host>/path")` and `.uri(uriBuilder -> uriBuilder.path("...").build())`. Extracts host and path separately. Emits `HttpCall` nodes. `confidence: high` for literal URI strings. This is a **concrete M1 deliverable** that did not exist at the Spike B calibration run and was the direct cause of 0% recall on petclinic.

**`spring-cloud-eureka`** (`spring-cloud-eureka` resolver, not a pack file) — a post-extraction linker pass that matches the `host_var` or `host` field of any `HttpCall` against every service's `spring.application.name` value read from `application.yml` / `bootstrap.yml` in all repos in the federation. When a match is found, the `HttpCall` is annotated with `resolved_service` and linked via a `CROSSES_TIER` edge with `confidence: medium`. This is a **concrete M1 deliverable** and closes the petclinic gap identified in Spike B.

### Express / Node

**`express-routes`** — detects `app.{get,post,put,delete,patch}(path, handler)` and `router.{get,...}` calls. Emits `Endpoint` nodes. Handles modular Express via `require()` tracking: a `RouterMount` node is emitted for each `app.use(prefix, require("./routes/x"))` and linked to the corresponding router file's endpoints at federation time. `confidence: high`.

**`kafkajs`** — detects `producer.send({topic, messages})` and `.subscribe({topic})` patterns from the kafkajs library. Emits `KafkaProducer` and `KafkaConsumer` nodes. `confidence: high` for literal topic strings.

**`js-fetch-hosted`** — detects `fetch(url)` and `axios.{get,post,...}(url)` calls where the URL contains a template-literal host variable (`${PERMITS_API}/api/...`). Captures `host_var` and the path segment separately for service-registry resolution. `confidence: high` for host variables that resolve through the registry; `medium` for unresolvable hosts.

### React

**`react-components`** — detects React functional components (arrow and named function forms) and class components. Emits `Component` nodes. Tracks `fetch` / `axios` calls made inside component bodies and emits `HttpCall` nodes linked to the component via a `CROSSES_TIER` edge. `confidence: high`.

### Auto-author skill

The auto-author skill (`discover-packs` + reviewed pack overlays) is a first-class M1 deliverable, not an experimental feature. It is the mechanism for extending coverage to frameworks outside the shipped set without writing engine code.

The loop: scan repo imports, annotations, method-call tokens, and `package.json` dependencies → subtract already-covered modules → for each uncovered candidate, render a prompt (schema + example packs + 3–5 sample files from the target repo) → submit to a model → validate the output by running the engine on the sample files and asserting nodes were emitted → save to `.cartograph/packs/<language>.json` as a reviewed overlay.

Auto-authored candidates are not used directly by M1. They are flagged for human review before becoming deterministic pack config. Once reviewed, their output is `source: pack:<rule-id>` like any other M1 pack. Unreviewed probabilistic extraction belongs to M1.5 and carries `source: llm:<model>@<date>`.

---

## Polyrepo federation

**Federation is Day-1, not deferred.** The graph schema namespace (`service` property on every node) is in place from the first commit. A single-repo index is a degenerate federation of one.

### Per-repo extraction

Each repo in the polyrepo is indexed independently. The output is a local graph JSON file with all node `id` values unqualified (local scope). The `service` name is read from a top-level `name` field in the repo's `cartograph.yaml`, falling back to the directory name.

### Service namespacing

After local extraction, all node `id` values are prefixed with `{service}:`. All edge `from` and `to` fields are rewritten to the prefixed form. This step is idempotent and reversible; the local graph file is preserved alongside the namespaced version.

### Merge

All namespaced per-repo graphs are merged into a single in-memory graph. Nodes with duplicate `id` values after namespacing are an error (indicates a collision in the caching key or a misconfigured `service` name).

### Cross-repo linker passes

Each linker pass reads the merged graph and emits new edges with `cross_repo: true`. Passes run in a fixed order; each is independently runnable for debugging.

**`link-http-via-service-registry`** — matches `HttpCall.host` or `HttpCall.host_var` against explicit host-to-service mappings in `service-registry.yaml`. Emits `CROSSES_TIER` edges. `confidence: high`.

**`link-http-via-eureka`** (`spring-cloud-eureka` resolver) — matches `HttpCall.host` against `spring.application.name` values from `application.yml` files across the federation. Emits `CROSSES_TIER` edges. `confidence: medium` (inferred, not explicit).

**`link-kafka-by-topic`** — matches `KafkaProducer.topic` against `KafkaConsumer.topics` across all services. Resolves topic variables via `ConfigProperty` default values before matching. Emits `KAFKA_DELIVERS` edges. `confidence: high` for literal topic matches; `medium` for variable-resolved matches.

---

## CGC importer

**Cartograph does not fork CodeGraphContext.** Instead, M1 ships a one-way importer that reads a CGC graph export (KuzuDB dump or JSON graph export) and re-emits its nodes into the Cartograph graph with `source: cgc-import`.

### Schema mapping

CGC uses a symbol-centric schema (functions, classes, call edges). The importer maps CGC node labels to the nearest Cartograph equivalents where a direct mapping exists:

| CGC label | Cartograph label | Notes |
|---|---|---|
| `Function` with HTTP annotation | `Endpoint` | Path and method extracted from decorator/annotation if present |
| `Function` (generic) | `Component` | `kind: cgc-function` |
| `Class` | `Service` | `kind: cgc-class` |
| `File` | `File` | Direct mapping |
| `CallEdge` | `CROSSES_TIER` | `confidence: low` — CGC call edges are symbol-level, not framework-semantic |

Nodes that cannot be mapped carry `label: CgcNode` and retain their original CGC properties verbatim. This preserves all CGC data in the graph for query access without requiring a perfect schema alignment at M1.

All imported nodes carry:
- `source: cgc-import`
- `confidence: low` (CGC's symbol-level extraction is not calibrated against Cartograph's framework-semantic targets)
- `service`: inferred from the CGC graph's repository metadata if present, otherwise set to the CGC graph file's stem name

The CGC-compat MCP shim (exposing Cartograph's graph through CGC's 21-tool surface) is an M2 deliverable, not M1.

---

## Default behaviour

### Test exclusion

Test paths are excluded by default at the engine level, before any pack rule runs. The full pattern list is in the [Pack engine](#pack-engine) section. Repositories can add more patterns in `cartograph.yaml`; the default cannot be silently disabled, and `include_test_paths: true` is required to include test paths.

### Producer dedup

The dedup pass runs after extraction and before any cross-repo linker. Key: `(service, file, line, topic-or-topic-var)`. Collisions are collapsed to the first-seen node; a `duplicate_count` property is set on the surviving node for observability. The pass applies to `KafkaProducer`, `HttpCall`, and any other call-site node label added in future packs.

### Confidence labels

Confidence is assigned by the rule that emits the node, not by a post-hoc scoring step. The assignment is deterministic:

- **`high`**: the key value (topic name, URL path, HTTP method) is a string literal in source. Zero ambiguity.
- **`medium`**: the key value is inferred — resolved through a `ConfigProperty` default, matched via Eureka `spring.application.name`, or assembled from a binary-expression URL chain. Correct in the majority of cases but structurally fallible.
- **`low`**: auto-authored pack output awaiting human review, or a CGC-imported node.

---

## Out of scope

The following are deliberately deferred and will not be accepted as M1 pull requests:

- **Web UI and graph visualisation** — M3 deliverable
- **Query API and MCP tools** — M2 deliverable; M1 produces a graph file, not a queryable service
- **LLM extraction (Layer 2)** — M1.5 deliverable; the pack-only baseline must be validated first
- **Agent-driven gap-filling (Layer 3)** — M2+ deliverable
- **gRPC code analysis** — M2 flagship; the proto parsing + generated-client matching problem spans multiple languages and is architecturally distinct from the pack model
- **RabbitMQ / AMQP extraction** — M2 add-on unless a real-repo calibration pass promotes it earlier; Kafka is the M1 message-bus target
- **Polyglot grammars beyond Java / JS / TS / Python** — Go and .NET are M2; the tree-sitter grammar integration and pack authoring for those languages is a distinct workstream
- **Kubernetes-manifest service resolver** — M2 alongside OpenTelemetry runtime-trace import
- **CGC-compat MCP shim** — M2; requires the query layer to be in place

---

## Success metrics

M1 is complete when the following calibration runs pass on the same target repos used in Spike B plus the second Kafka regression corpus.

**Primary targets:**

| Repo | Metric | Target | Spike B baseline |
|---|---|---|---|
| `piomin/sample-spring-kafka-microservices` | Precision (service-pair) | ≥ 95% | 100% after fixes |
| `piomin/sample-spring-kafka-microservices` | Recall (cross-repo Kafka edges) | ≥ 90% | 100% after fixes |
| `spring-petclinic/spring-petclinic-microservices` | Precision (cross-repo HTTP) | ≥ 95% | 0% (no WebClient pack) |
| `spring-petclinic/spring-petclinic-microservices` | Recall (cross-repo HTTP edges) | ≥ 90% | 0% (no Eureka resolver) |
| `ewolff/microservice-kafka` | Precision (topic delivery) | ≥ 95% | New M1 regression target |
| `ewolff/microservice-kafka` | Recall (order topic consumers) | ≥ 90% | New M1 regression target |

The piomin 100/100 result from Spike B ([`spike/real-repos/SPIKE-B-FINDINGS.md`](../spike/real-repos/SPIKE-B-FINDINGS.md)) is the proof point that these targets are reachable. The petclinic 0/0 result defines the two specific packs (`spring-webclient`, `spring-cloud-eureka`) whose completion gates the M1 close.

**Secondary targets (no regressions):**

- The CityPermits polyrepo fixture from Spike A must still produce ≥ 92 nodes / 25 edges with all 8 cross-repo HTTP edges and 3 Kafka delivery edges intact.
- Auto-author skill must produce a runnable pack (zero engine validation errors) on at least one new framework not in the shipped set, in a single loop iteration.
- The large Java workspace assembled from Petclinic + Piomin + Ewolff must index as a single federation with zero duplicate service-prefixed node IDs.
- The large Java workspace must emit no `KAFKA_DELIVERS` or `CROSSES_TIER` edge whose source or target file is under a default-excluded path.

**Required CI gates:**

```bash
python scripts/prepare_real_repos.py
cartograph index --workspace fixtures/real-java-workspace --out out/m1-real-java.graph.json
cartograph verify --graph out/m1-real-java.graph.json --suite fixtures/expectations/m1-real-java.yaml
cartograph index --workspace .cartograph-real-repos/workspace --out cartograph-out/real-repos.graph.json --report cartograph-out/GRAPH_REPORT.md
cartograph verify --graph cartograph-out/real-repos.graph.json --suite fixtures/expectations/m1-real-java.yaml
cartograph verify --graph out/citypermits.graph.json --suite fixtures/expectations/citypermits-m1.yaml
```

The `m1-real-java.yaml` verifier owns the corpus-specific assertions: service list, expected Kafka topic links, expected Petclinic HTTP links, duplicate-ID check, confidence-tier check, and test-path exclusion check. The CityPermits verifier owns the Spike A regression numbers.

**Agent integration gate:** `cartograph install --platform codex --project <tmpdir>` must write a Cartograph skill, `AGENTS.md`, and a Codex hook config. The installed instructions must tell the agent to consult `cartograph-out/GRAPH_REPORT.md` and use graph commands before broad source search, while still allowing source reads for edits and debugging.

**The test-exclusion and dedup defaults must remain on.** Any PR that makes these opt-in rather than opt-out will be rejected on the grounds that it reverts the Spike B precision gain.

---

## Open questions

1. **`spring-cloud-eureka` resolver scope.** The resolver reads `spring.application.name` from `application.yml` files across all repos in the federation. This works when all repos are co-located (monorepo-style checkout or CI workspace). For the case where repos are checked out separately and the service registry is the only shared artifact, does the Eureka resolver need to be driven from the registry file alone, or is a full multi-repo checkout a reasonable M1 requirement? *Owner: indexing team.*

2. **Large-workspace fixture ownership.** The real Java workspace is assembled from upstream open-source projects. Who owns pinning commits, refreshing expected edges, and auditing upstream changes that add or remove services? *Owner: QA lead.*

3. **CGC importer file format stability.** CGC v0.4.9 exports graphs as KuzuDB dumps. If CGC releases a breaking schema change before M1 ships, the importer may need to target a pinned CGC version. Should we target the JSON export format instead of the binary KuzuDB dump to reduce coupling? *Owner: integrations team.*
