# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

Cartograph is a graph-first code intelligence tool for polyrepo systems. It indexes services, endpoints, HTTP calls, message handlers, database queries, and cross-service contracts into a federated graph, then answers structural questions about that graph. The model is framework-centric (Endpoint, HttpCall, KafkaProducer, MessageConsumer), not symbol-centric.

## Commands

```bash
python -m pytest tests/                                                            # all tests
python -m pytest tests/test_layers_m1.py::test_name                                # single test
python -m cartograph index --workspace <path> --out cartograph-out/graph.json
python -m cartograph index --workspace <path> --lens-dir .cartograph/lenses --out ...   # with overlay lenses
python -m cartograph serve --graph cartograph-out/graph.json                       # JSON-lines MCP-style server
python -m cartograph tools
python -m cartograph verify --graph <graph.json> --suite <suite.json>
```

Dependencies: Python 3.11+, `tree-sitter`, `tree-sitter-java`, `tree-sitter-javascript` (see `pyproject.toml`). No other runtime deps.

After `cartograph index`, the CLI prints any unresolved linking gaps to stdout with concrete next steps. Read that output — it's how the tool tells you what's missing.

## Architecture

### Pipeline (cartograph/indexer.py)

1. Discover services (`cartograph.yaml`, `package.json`, or `pom.xml`)
2. Run `scope: source` lenses on each file — emit nodes/edges via regex, annotation-method, token-line, xml-element, config-key, or tree-sitter strategies
3. Run `scope: resolve` lenses on the node list — parse raw captured fields into structured ones (e.g. URL → host+path)
4. Apply `resolve-hints.json` from workspace root — per-node patches for one-off gaps
5. Load `service-registry.yaml` and run the linker — produces `CROSSES_TIER`, `KAFKA_DELIVERS`, `MESSAGE_DELIVERS` edges
6. Record everything the linker couldn't connect in `graph.meta.unresolved` so the agent can investigate and patch

### Lens-first design contract (CRITICAL)

Framework knowledge lives in JSON lenses (`cartograph/lens_defs/*.json` built-in, `.cartograph/lenses/*.json` overlay). Engine code (`engine.py`, `linkers.py`, `tree_sitter_strategy.py`, `lens_runner.py`, `indexer.py`) stays framework-agnostic — it implements generic strategies, not framework-specific logic.

Adding a new framework? Write a lens, not Python. The `.claude/hooks/lens_discipline.py` PreToolUse hook blocks framework tokens in engine files. See `.claude/skills/add-framework-support/SKILL.md` for the workflow.

Three lens scopes:
- `source` — match files, emit nodes/edges
- `resolve` — parse raw fields on existing nodes into structured fields via regex (e.g. extract `host` from `url`)
- `graph` — Cypher-style queries against the indexed graph

### Graph Model

`cartograph/graph.py` — `Graph` dataclass with nodes, edges, meta, and a `SchemaRegistry` (`cartograph/models.py`). Every node/edge carries `source` (e.g. `lens:spring-rest-endpoint`) and `confidence` (`high`/`medium`/`low`). Node IDs are service-namespaced: `{service}:{file}:{line}:{hash}`.

Common node labels: `Service`, `Endpoint`, `HttpCall`, `KafkaProducer`, `KafkaConsumer`, `MessageProducer`, `MessageConsumer`, `Component`, `ConfigProperty`, `Action`, `Servlet`, `DatabaseQuery`. Schemas per label are recorded in `graph.meta.schema` so you can introspect what fields exist.

Key edge types: `HANDLES`, `CROSSES_TIER` (cross-service HTTP), `KAFKA_DELIVERS`, `MESSAGE_DELIVERS`, `HANDLES_KAFKA`, `HANDLES_MESSAGE`, `CONTAINS`, `EMITS`.

### Query Layer

`cartograph/query.py` — `flow`, `find_callers`, `find_callees`, `endpoints_in_service`, `cross_service_edges`, `kafka_topics`, `search`, `lens`, `explain_flow`, `coverage_report`, `cgc_tool`. Search uses weighted field scoring with label-priority tie-breaking (Endpoint > HttpCall > Component > Service). The `lens` function dispatches between configured `kuzu-cypher` lenses, built-in `pattern.*`, and dynamically generated `route.*` and `domain.*` lenses.

Cypher subset for `graph` lenses lives in `cartograph/lens_specs.py` (`run_kuzu_query_subset`). Real Kuzu integration is scaffolded but not wired.

### Refinement loop

When `cartograph index` finishes with non-empty `meta.unresolved`, close gaps in this order (cheapest first):

1. `<workspace>/service-registry.yaml` — flat `hostname: service-name` map. Use when a host name in code doesn't match a service directory name (Spring Cloud names, Feign `name = ...`, Docker hostnames).
2. `.cartograph/lenses/*.json` with `scope: resolve` — parse raw captures into structured fields (e.g. split URL into host+path). Use when the same pattern recurs across many nodes.
3. `<workspace>/resolve-hints.json` — array of `{match: {...}, set: {...}}` patches. Use for one-off gaps where the host comes from a runtime env var that static analysis can't see.
4. New `.cartograph/lenses/*.json` source lens — when the framework or pattern isn't recognized at all.

Detailed playbook: `.apm/skills/cartograph/references/refinement-loop.md`.

### Extensibility surfaces

- **Lenses**: `cartograph/lens_defs/*.json` (built-in) and `.cartograph/lenses/*.json` (project overlay via `--lens-dir`). Name collisions: overlay wins.
- **Plugins** (`cartograph/plugins.py`): Local Python run via `run-plugin --allow-plugin`.
- **CGC compat** (`cartograph/cgc.py`): Imports CodeGraphContext JSON.
- **MCP server** (`cartograph/serve.py`): JSON-lines stdin/stdout with `tools/list` and `tools/call`.

### Service Configuration

Each service can have a `cartograph.yaml` with `name`, `exclude` patterns, `include_test_paths`, and `metadata`. A workspace-level `service-registry.yaml` maps hostnames to service names for cross-service HTTP linking.

### Discipline tooling (.claude/)

- `.claude/hooks/lens_discipline.py` — PreToolUse hook that blocks framework-specific tokens in engine files (`engine.py`, `linkers.py`, `tree_sitter_strategy.py`, `lens_runner.py`). Override with `CARTOGRAPH_LENS_GUARD=off` if genuinely needed (rare).
- `.claude/agents/lens-discipline-reviewer.md` — subagent for shape-level review the hook can't catch (e.g. generic-shaped helpers that only serve one framework).
- `.claude/skills/add-framework-support/SKILL.md` — walks the lens-first workflow when adding any new framework.

### Real-repo fixtures

`.cartograph-real-repos/` contains cloned production codebases (Spring PetClinic, FTGO, PiggyMetrics) used for end-to-end validation. Re-index after lens changes to confirm edges hold and unresolved counts don't regress.

## Key Design Decisions

- Test paths excluded by default (`src/test/**`, `__tests__/**`, etc.) — the difference between 12.5% and 100% precision
- Producer/call-site dedup is default engine behavior (`linkers.dedup_call_sites`)
- Node IDs are service-namespaced: `{service}:{file}:{line}:{hash}`
- No YAML parser dependency — `parse_simple_yaml` in `cartograph/discovery.py` handles the subset needed
- Cross-service linking is the linker's job; it never modifies node content, only adds edges and records unresolved gaps
- Tree-sitter is required (not optional) — Java/JS structural matching uses it; regex is fallback for plain text / config files
- Fixtures in `fixtures/` are minimal multi-service workspaces; `.cartograph-real-repos/` holds full production clones for validation
