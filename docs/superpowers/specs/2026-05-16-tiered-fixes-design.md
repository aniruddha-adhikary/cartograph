# Cartograph Tiered Fix Plan

**Date:** 2026-05-16
**Goal:** Make Cartograph contributor-ready by addressing six structural issues in priority order.
**Status:** All three milestones (M1, M1.5, M2) are at prototype quality — internals can be reshaped freely.

---

## Key Design Decision: Unified Lens Model

The current codebase has three overlapping concepts:
- **Packs** — index-time extraction rules (source code → graph nodes/edges)
- **Views** — simple graph projections (filter nodes/edges by label/type)
- **Lenses** — query-time graph pattern matching (Kuzu Cypher subset)

These converge into a single concept: **Lens**. A lens is a declarative rule that describes how to see the codebase. It has two execution modes:

- `scope: source` — matches against source files, emits graph nodes/edges (replaces packs)
- `scope: graph` — matches against the built graph, returns projected subgraphs (replaces views + lenses)

One format, one schema, one CLI, one engine. Claude doesn't need to know it's writing an "extractor" vs. a "query" — it writes a lens.

## Key Design Decision: CLI-Only Interface

Cartograph is a CLI tool driven by Claude Code through Bash. There is no MCP server. `serve.py` is deleted.

- **Indexing and authoring** happen through CLI commands during development
- **Querying** happens through CLI commands that Claude invokes via Bash
- Claude reads stdout to get results

## Key Design Decision: LLM-Assisted Bootstrap

When Cartograph encounters unfamiliar frameworks, Claude Code proposes new lenses (not one-off extractions). The loop:

1. `cartograph discover` detects unrecognized patterns in source code
2. Claude reads discovery output + sample files + the lens schema
3. Claude drafts new lenses in the standard JSON format
4. `cartograph test-lens` dry-runs proposed lenses against source files
5. User approves, `cartograph persist-lens` writes them as overlays
6. Next `cartograph index` run uses them — deterministic, free, auditable

The LLM's output is a reusable rule, not a one-off extraction. The system gets smarter over time without accumulating LLM cost.

---

## Tier 1: Unified Lens Format + Generic Engine

### Problem

Extraction logic is split between pack JSON configs (which describe *what* to look for) and hardcoded Python in `indexer.py` (which describes *how* to extract). A new framework requires editing Python, not just adding config. Meanwhile, the query side has its own separate config formats (views, lenses) with a hand-rolled Cypher interpreter.

### Design

#### Lens Schema

Every lens is a JSON object with:

```json
{
  "name": "spring-rest-endpoint",
  "scope": "source",
  "match": {
    "files": ["*.java"],
    "class_annotations": ["@RestController", "@Controller"],
    "base_path": { "annotation": "@RequestMapping", "capture": "value" },
    "method_annotations": {
      "GetMapping": "GET",
      "PostMapping": "POST",
      "PutMapping": "PUT",
      "DeleteMapping": "DELETE",
      "PatchMapping": "PATCH"
    }
  },
  "emit": {
    "label": "Endpoint",
    "path": "{{base_path}}/{{method_path}}",
    "http_method": "{{http_method}}",
    "handler": "{{class}}.{{method}}",
    "source": "pack:spring-rest-endpoint",
    "confidence": "high"
  }
}
```

```json
{
  "name": "kafka-bus-view",
  "scope": "graph",
  "match": {
    "query": "MATCH (p:KafkaProducer)-[d:KAFKA_DELIVERS]->(c:KafkaConsumer) RETURN p, d, c"
  },
  "emit": {
    "returns": { "p": "KafkaProducer", "d": "KAFKA_DELIVERS", "c": "KafkaConsumer" }
  }
}
```

#### Engine (`cartograph/engine.py`)

A generic loop:
1. Load lens definitions (built-in + overlay directories)
2. For `scope: source`: iterate files matching the lens's file patterns, run matchers, apply emit templates, produce typed nodes/edges
3. For `scope: graph`: run the match query against the graph, apply projections, return results

No framework-specific logic in the engine. All framework knowledge — including node/edge schemas — lives in lens definitions.

#### CLI Commands

```bash
# Indexing
cartograph index --workspace ./repos --out graph.json
cartograph discover --workspace ./repos

# Querying
cartograph flow --graph graph.json --anchor "motor-vehicle"
cartograph search --graph graph.json --query "permits"
cartograph lens --graph graph.json --name "kafka-bus-view"
cartograph explain --graph graph.json --anchor "motor-vehicle"
cartograph list-lenses --graph graph.json

# Lens authoring
cartograph test-lens --lens proposed.json --workspace ./repos
cartograph persist-lens --lens proposed.json --out .cartograph/lenses/django.json
```

#### Overlay Mechanics

Lens overlays work like current pack overlays. Project-level overrides in `.cartograph/lenses/` extend built-in lenses. Lists extend, not replace, via deep merge. A workspace can have:

```
.cartograph/
  lenses/
    django.json       # project-specific source lenses
    team-queries.json  # project-specific graph lenses
```

### Files Changed

- **New:** `cartograph/engine.py` — generic lens execution engine
- **New:** `cartograph/lenses/` directory — built-in lens definitions (replaces `cartograph/packs/`)
- **Rewrite:** `cartograph/schema.py` — unified lens schema validation
- **Delete:** `cartograph/packs/spring.json`, `cartograph/packs/javascript.json` — replaced by lens definitions
- **Delete:** `cartograph/views/default.json` — replaced by `scope: graph` lenses
- **Delete:** `cartograph/views.py` — absorbed into engine
- **Delete:** `cartograph/serve.py` — no MCP server
- **Modify:** `cartograph/cli.py` — add lens authoring commands

### Migration

Convert existing pack configs to `scope: source` lens definitions. Convert existing view specs and Kuzu lens specs to `scope: graph` lens definitions. Run golden tests to verify identical graph output.

---

## Tier 2: Schema-Driven Graph Model

### Problem

`Graph` stores `list[dict[str, Any]]` for nodes and edges. No validation, no discoverability, silent bugs from field name typos. But hardcoding Python dataclasses per node/edge type (Endpoint, KafkaProducer, etc.) is equally rigid — if Claude bootstraps a gRPC or RabbitMQ lens at runtime, it shouldn't need to also add a Python class.

### Design Principle

The lens that emits a node defines what fields that node has. The type system is schema-driven, not class-driven. No Python class needed per node type — the lens definition *is* the type.

#### Universal Base Types (Python)

Two Python classes enforce the fields every node and edge must have:

```python
@dataclass
class Node:
    id: str
    label: str
    service: str
    file: str
    line: int
    source: str
    confidence: Literal["high", "medium", "low"]
    props: dict[str, Any] = field(default_factory=dict)  # lens-defined fields

    def get(self, key: str, default=None):
        return self.props.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "service": self.service,
                "file": self.file, "line": self.line, "source": self.source,
                "confidence": self.confidence, **self.props}

@dataclass
class Edge:
    type: str
    from_id: str
    to_id: str
    source: str
    confidence: Literal["high", "medium", "low"]
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "from": self.from_id, "to": self.to_id,
                "source": self.source, "confidence": self.confidence, **self.props}
```

Universal fields are enforced by Python. Everything else lives in `props` and is validated against the lens's emit schema.

#### Lens Emit Schema

Each lens declares the schema of what it produces:

```json
{
  "name": "spring-rest-endpoint",
  "scope": "source",
  "match": { "..." },
  "emit": {
    "label": "Endpoint",
    "schema": {
      "path": "string",
      "http_method": "string",
      "handler": "string"
    },
    "values": {
      "path": "{{base_path}}/{{method_path}}",
      "http_method": "{{http_method}}",
      "handler": "{{class}}.{{method}}"
    },
    "source": "lens:spring-rest-endpoint",
    "confidence": "high"
  }
}
```

A gRPC lens would declare its own shape without touching Python:

```json
{
  "name": "grpc-service-method",
  "scope": "source",
  "match": { "..." },
  "emit": {
    "label": "GrpcMethod",
    "schema": {
      "service_name": "string",
      "rpc_method": "string",
      "streaming": "boolean",
      "request_type": "string",
      "response_type": "string"
    },
    "values": { "..." },
    "source": "lens:grpc-service-method",
    "confidence": "high"
  }
}
```

#### Runtime Validation

The engine validates emitted nodes/edges against the lens's own emit schema:
- At **lens-load time**: schema is well-formed (valid field names, known types)
- At **emit time**: produced values match declared types, no undeclared fields
- At **query time**: `cartograph list-lenses` reports the full schema of every node/edge type in the graph

#### Schema Registry

The graph carries a schema registry in its `meta` block — the union of all emit schemas from all lenses that contributed to it:

```json
{
  "meta": {
    "schema": {
      "node_labels": {
        "Endpoint": { "path": "string", "http_method": "string", "handler": "string" },
        "GrpcMethod": { "service_name": "string", "rpc_method": "string", "streaming": "boolean" }
      },
      "edge_types": {
        "CROSSES_TIER": { "from_service": "string", "to_service": "string" },
        "KAFKA_DELIVERS": { "from_service": "string", "to_service": "string", "topic": "string" }
      }
    }
  }
}
```

This means:
- `scope: graph` lenses can validate their queries against known labels/types at load time
- Claude can read the schema registry to understand what's in a graph before querying it
- KuzuDB table creation (Tier 5) is driven by the schema registry, not hardcoded

#### Serialization

`Node.to_dict()` flattens universal fields + props into a single dict. The JSON format is unchanged — existing golden test fixtures remain valid. `from_dict()` splits known universal fields from everything else into `props`.

### Files Changed

- **New:** `cartograph/models.py` — `Node`, `Edge` base types + schema registry logic
- **Modify:** `cartograph/graph.py` — `Graph` holds `list[Node]` and `list[Edge]`, `meta` includes schema registry
- **Modify:** `cartograph/engine.py` — emit produces `Node`/`Edge` objects, validates against lens schema
- **Modify:** `cartograph/query.py` — uses `node.get("path")` via props accessor (minimal change)

### Migration

1. Introduce `Node` and `Edge` types with `props` bag
2. Engine emits typed objects, `to_dict()` at serialization boundary
3. Query layer loads via `from_dict()`, uses `.get()` accessor (same API as dict)
4. Build schema registry from lens definitions during indexing
5. Once stable, remove raw dict code paths

---

## Tier 3: Indexer Decomposition

### Problem

Even with the lens engine handling extraction, `indexer.py` still handles service root discovery, config loading, cross-service linking, dedup, and lens persistence in one file. A contributor shouldn't need to read all of it to understand any part.

### Design

Split along responsibility lines:

```
cartograph/
  indexer.py       — orchestrator only (~100 lines)
  engine.py        — generic lens engine (from Tier 1)
  discovery.py     — service root detection (evolves from discover.py)
  config.py        — lens loading, merging, deep_merge, YAML parsing
  linkers.py       — cross-service HTTP + message bus linking
  dedup.py         — producer/call-site deduplication
  lenses.py        — lens persistence into graph
```

#### Orchestrator

```python
def index_workspace(workspace, registry_path=None, lenses_dir=None):
    roots = discover_service_roots(workspace)
    lens_config = load_lens_config(workspace, lenses_dir)
    graph = Graph()

    for root in roots:
        context = build_service_context(root, lens_config)
        nodes, edges = engine.run_source_lenses(lens_config.source_lenses, context)
        graph.add_all(nodes, edges)

    link_http(graph, load_registry(registry_path))
    link_messages(graph)
    deduplicate(graph)
    persist_lenses(graph)
    return graph
```

Each module has one job, one test file, clear inputs/outputs.

### Constraint

Pure refactor — no behavior changes. Golden test output must be identical before and after.

### Files Changed

- **Rewrite:** `cartograph/indexer.py` — slim orchestrator
- **New:** `cartograph/config.py` — lens loading and merging extracted from indexer
- **New:** `cartograph/linkers.py` — HTTP and message linking extracted from indexer
- **New:** `cartograph/dedup.py` — deduplication extracted from indexer
- **Evolve:** `cartograph/discover.py` → `cartograph/discovery.py` — absorbs service root detection from indexer

---

## Tier 4: Tree-sitter for `scope: source` Lenses

### Problem

Source lenses use regex over raw text. This can't handle multiline annotations, nested generics, or structural patterns like "method inside a class annotated with X." The strategy doc names tree-sitter as a dependency but it's absent from the codebase.

### Design

The lens match spec for `scope: source` gains tree-sitter support:

```json
{
  "name": "spring-rest-endpoint",
  "scope": "source",
  "match": {
    "language": "java",
    "query": "(method_declaration (modifiers (annotation name: (identifier) @ann)) name: (identifier) @method)",
    "where": { "ann": ["GetMapping", "PostMapping", "PutMapping"] }
  },
  "emit": { "..." }
}
```

#### Two Matcher Backends

- **`regex`** — current behavior, no dependency, works for simple patterns
- **`tree-sitter`** — structural AST queries, handles multiline/nested patterns

A lens specifies which backend via the match format. If `query` is present, tree-sitter. If `pattern` is present, regex. Regex lenses keep working — nothing breaks.

#### Dependency

`tree-sitter` + language grammar packages (`tree-sitter-java`, `tree-sitter-javascript`, `tree-sitter-python`). Pip-installable. Grammars load lazily — only parse Java if source lenses targeting `*.java` exist.

#### What This Unlocks

Claude can author lenses that match on AST structure. "Find all methods annotated with X inside classes annotated with Y that return type Z" becomes a tree-sitter query instead of a fragile multi-regex chain.

### Files Changed

- **Modify:** `cartograph/engine.py` — add tree-sitter matcher alongside regex matcher
- **New:** `cartograph/matchers/tree_sitter.py` — tree-sitter query execution
- **New:** `cartograph/matchers/regex.py` — existing regex logic extracted
- **Modify:** `pyproject.toml` — add tree-sitter dependencies (optional extras)

---

## Tier 5: KuzuDB for `scope: graph` Lenses

### Problem

`lens_specs.py` hand-rolls a Cypher subset via regex parsing and nested-loop joins over Python lists. No indexing, no aggregation, no path expressions. O(bindings x edges) per clause.

### Design

Graph lenses already use Kuzu Cypher syntax. Replace the hand-rolled interpreter with embedded KuzuDB:

```
cartograph index → produces graph.json
cartograph lens --name X → loads graph into KuzuDB in-memory → runs real Cypher → returns results
```

#### Migration

Existing `scope: graph` lenses should run against real KuzuDB with minimal query adjustments. The hand-rolled `parse_query`, `match_clause`, `condition_matches` (~200 lines in `lens_specs.py`) get replaced by `connection.execute(query)`.

#### What Stays

Lens schema, validation, `returns` type checking, parameter substitution. These wrap the KuzuDB call.

#### What Goes

The entire hand-rolled pattern matching, binding, and join logic in `lens_specs.py`.

#### Graph Loading

KuzuDB is embedded (like SQLite). For a CLI tool, loading `graph.json` into KuzuDB per command is acceptable. For larger graphs, a warm background process is a future option but not needed now.

### Files Changed

- **Rewrite:** `cartograph/lens_specs.py` — KuzuDB execution replaces hand-rolled interpreter
- **Modify:** `pyproject.toml` — add `kuzu` dependency

---

## Tier 6: Search Improvements

### Problem

Hardcoded synonym table (`automobile -> motor, vehicle`), weighted field scoring tuned to test fixtures, no real retrieval strategy.

### Design

With KuzuDB in place, search collapses into graph lenses:

#### Search as a Lens

```json
{
  "name": "search.default",
  "scope": "graph",
  "match": {
    "query": "MATCH (n) WHERE n.path CONTAINS $term OR n.handler CONTAINS $term OR n.name CONTAINS $term RETURN n"
  },
  "params": { "term": "" }
}
```

Search becomes `cartograph lens --name search.default --params '{"term": "permits"}'`. No special-cased function.

#### Drop the Synonym Table

Claude handles query expansion. Claude knows what the user means by "automobile" — it can issue multiple searches or rewrite the query before calling `cartograph search`. The tool doesn't need to be smart about synonyms; the caller already is.

#### What Gets Deleted

`expand_query_tokens`, `search_score`, `search_fields`, `rank_search_candidates`, the synonym table — ~100 lines of hand-tuned retrieval logic replaced by graph queries and Claude's own intelligence.

### Files Changed

- **Modify:** `cartograph/query.py` — `search()` delegates to graph lens execution
- **Delete:** synonym table, weighted field scoring, `rank_search_candidates`
- **New:** `cartograph/lenses/search.json` — built-in search lenses

---

## Deleted Components

| File | Reason |
|------|--------|
| `cartograph/serve.py` | No MCP server. CLI-only. |
| `cartograph/packs/spring.json` | Replaced by `scope: source` lens definitions |
| `cartograph/packs/javascript.json` | Replaced by `scope: source` lens definitions |
| `cartograph/views/default.json` | Replaced by `scope: graph` lens definitions |
| `cartograph/views.py` | Absorbed into lens engine |
| `cartograph/tools.py` | MCP tool catalog, no longer needed |

---

## Dependency Summary

| Tier | New Dependencies |
|------|-----------------|
| 1-3 | None (stdlib only) |
| 4 | `tree-sitter`, `tree-sitter-java`, `tree-sitter-javascript`, `tree-sitter-python` (optional extras) |
| 5 | `kuzu` |
| 6 | None |

---

## What Stays as Python (Not Lenses)

The following query functions in `query.py` are graph traversal algorithms, not declarative patterns. They stay as Python functions exposed via CLI commands:

- `flow` — BFS walk from an anchor node, following specific edge types, with depth control
- `explain_flow` — human-readable narration of a flow trace
- `find_callers` / `find_callees` — directed edge traversal from matched nodes
- `cross_service_edges` — filtered edge listing
- `kafka_topics` — topic aggregation with producer/consumer grouping
- `coverage_report` — per-service source/confidence breakdown
- `cgc_tool` — CGC compatibility shim (may be removed if no longer needed)

These are algorithms with control flow (BFS queues, depth limits, same-service producer heuristics) that don't reduce to declarative Cypher. They consume the graph that lenses build.

---

## Node/Edge Types Are Runtime Constructs

There are no hardcoded Python classes for Endpoint, KafkaProducer, CrossesTier, etc. The lens that emits a node declares its schema. The graph's `meta.schema` registry is the union of all emit schemas. This means:

- Claude can invent new node/edge types at runtime by writing a lens with a new emit schema
- `scope: graph` lenses validate their queries against the schema registry
- KuzuDB table creation (Tier 5) is driven by the schema registry
- `cartograph list-lenses` shows what types exist and what fields they have

---

## Source Lens Match Format Evolution

The `scope: source` match format has two generations:

**Tier 1 (regex era):** Structured fields like `class_annotations`, `method_annotations`, `base_path`. These are framework-oriented shorthands that the regex matcher interprets. They work for annotation-driven frameworks (Spring, Express) but are not general-purpose.

**Tier 4 (tree-sitter era):** Raw tree-sitter `query` strings that match AST structure directly. These are general-purpose and replace the structured fields for any lens that needs structural matching.

Both formats coexist. Simple lenses (e.g., "find lines matching this regex") use the Tier 1 format. Complex lenses (e.g., "methods inside annotated classes") use tree-sitter queries. The engine dispatches based on which fields are present in the match spec.

---

## Ordering Constraints

- Tier 2 depends on Tier 1 (emit schemas live in lens definitions)
- Tier 3 depends on Tier 1 (orchestrator runs lens engine)
- Tier 4 depends on Tier 1 (tree-sitter is an alternative matcher backend for the lens engine)
- Tier 5 depends on Tier 1 (KuzuDB is an alternative executor for graph lenses)
- Tier 6 depends on Tier 5 (search-as-lens needs KuzuDB)
- Tiers 4 and 5 are independent of each other and can be done in parallel
