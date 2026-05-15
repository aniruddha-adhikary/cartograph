# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Cartograph is an AI-first knowledge-graph code intelligence tool for polyrepo systems. It builds a federated graph across multiple services, indexing endpoints, message handlers, HTTP calls, and cross-service contracts. The graph is framework-centric (endpoints, flows, contracts) rather than symbol-centric (functions, classes, calls).

## Commands

```bash
# Run all tests
python -m pytest tests/

# Run a single test
python -m pytest tests/test_layers_m1.py::test_name

# Index a workspace
python -m cartograph index --workspace <path> --out cartograph-out/graph.json

# Run the JSON-lines MCP-style query server
python -m cartograph serve --graph cartograph-out/graph.json

# List available tools
python -m cartograph tools

# Verify a graph against expectations
python -m cartograph verify --graph <graph.json> --suite <suite.json>
```

No external dependencies beyond Python 3.11+ stdlib. The project uses setuptools for packaging (`pyproject.toml`).

## Architecture

### Core Pipeline

The indexer (`cartograph/indexer.py`) is the heart of the system. It:
1. Discovers service roots in a workspace (directories with `cartograph.yaml`, `package.json`, or `pom.xml`)
2. Indexes each service by scanning source files with regex-based extractors (not tree-sitter yet)
3. Runs cross-service linkers to create HTTP and message delivery edges
4. Deduplicates producers/call sites and edges
5. Persists auto-generated lenses into the graph

### Three-Layer Design (Milestones)

- **Layer 1 (Packs)** - M1, currently implemented. Deterministic regex extraction via JSON pack configs (`cartograph/packs/spring.json`, `cartograph/packs/javascript.json`). Handles Spring REST, Kafka, Express, Struts, J2EE servlets, SQL, Spring Cloud Gateway.
- **Layer 2 (LLM extraction)** - M1.5, not yet implemented. For frameworks packs can't reach.
- **Layer 3 (Agents)** - M2, not yet implemented. Query-time intelligence via LangGraph.

### Graph Model

`cartograph/graph.py` — `Graph` dataclass with nodes, edges, and meta. Every node and edge carries `source` (e.g. `pack:spring-rest-controller`) and `confidence` (`high`/`medium`/`low`).

Key node labels: `Service`, `Endpoint`, `HttpCall`, `KafkaProducer`, `KafkaConsumer`, `MessageProducer`, `MessageConsumer`, `Component`, `File`, `ConfigProperty`, `Action`, `Servlet`, `DatabaseQuery`, `Lens`.

Key edge types: `HANDLES`, `CROSSES_TIER` (cross-service HTTP), `KAFKA_DELIVERS`, `MESSAGE_DELIVERS`, `HANDLES_KAFKA`, `HANDLES_MESSAGE`, `CONTAINS`, `EMITS`.

### Query Layer

`cartograph/query.py` — All graph queries: `flow`, `find_callers`, `find_callees`, `endpoints_in_service`, `cross_service_edges`, `kafka_topics`, `search`, `lens`, `explain_flow`, `coverage_report`, `cgc_tool`. The `search` function uses weighted field scoring with deterministic fallback (no embeddings).

### Extensibility

- **Pack overlays**: Project-level overrides in `.cartograph/packs/` or `--packs-dir`. Lists extend (not replace) defaults via `deep_merge`.
- **Views** (`cartograph/views.py`): JSON-configured node/edge projections in `cartograph/views/default.json`, overridable via layers.
- **Lenses** (`cartograph/lens_specs.py`): Named query templates (Kuzu Cypher syntax). Built-in pattern lenses (`pattern.endpoints`, `pattern.kafka_bus`, etc.) plus configured and persisted lenses.
- **Layers** (`cartograph/layers.py`): Stackable config directories (project `.cartograph/` + explicit `--layer-dir`), each with `packs/`, `views/`, `lenses/` subdirs.
- **Plugins** (`cartograph/plugins.py`): Local Python scripts run against a graph via `run-plugin --allow-plugin`.
- **CGC compat** (`cartograph/cgc.py`): Imports CodeGraphContext JSON exports. `cgc_tool` adapter maps CGC tool names to Cartograph queries.

### MCP Server

`cartograph/serve.py` — JSON-lines stdin/stdout protocol. Supports `tools/list` and `tools/call` methods, dispatching to all query functions.

### Service Configuration

Each service can have a `cartograph.yaml` with `name`, `exclude` patterns, `include_test_paths`, and `metadata`. A workspace-level `service-registry.yaml` maps hostnames to service names for cross-service HTTP linking.

## Key Design Decisions

- Test paths excluded by default (the difference between 12.5% and 100% precision)
- Producer/call-site dedup is default engine behavior
- Node IDs are service-namespaced: `{service}:{file}:{line}:{hash}`
- No YAML parser dependency — `parse_simple_yaml` in indexer handles the subset needed
- Fixtures in `fixtures/` include multi-service Java workspaces and expectation files for verification
