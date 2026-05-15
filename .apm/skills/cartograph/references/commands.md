# Cartograph Command Reference

## Indexing

```bash
# Index the current workspace
cartograph index --workspace . --out cartograph-out/graph.json

# With a project lens overlay directory
cartograph index --workspace . --lens-dir .cartograph/lenses --out cartograph-out/graph.json

# With a custom service registry
cartograph index --workspace . --registry-path service-registry.yaml --out cartograph-out/graph.json
```

The indexer discovers services (directories containing `cartograph.yaml`, `package.json`, or `pom.xml`), runs `source` lenses on each source file, runs `resolve` lenses on the emitted nodes, applies `resolve-hints.json` if present, then runs the linker to create cross-service edges.

## Task → Command mapping

| User asks | Run |
|---|---|
| "What happens when X runs?" | `cartograph explain --graph cartograph-out/graph.json --anchor <X>` |
| "Show the flow for X" | `cartograph flow --graph cartograph-out/graph.json --anchor <X>` |
| "Who calls X?" | `cartograph find-callers --graph cartograph-out/graph.json --symbol <X>` |
| "What does X call?" | `cartograph find-callees --graph cartograph-out/graph.json --symbol <X>` |
| "What endpoints does service S expose?" | `cartograph endpoints-in-service --graph cartograph-out/graph.json --service <S>` |
| "Which topics/events reach S?" | `cartograph kafka-topics --graph cartograph-out/graph.json --consumer-service <S>` |
| "Show cross-service calls from S" | `cartograph cross-service-edges --graph cartograph-out/graph.json --from-service <S>` |
| "Where should I edit?" | `cartograph search --graph cartograph-out/graph.json --query <terms>` |
| "What lenses can I run?" | `cartograph lens list --graph cartograph-out/graph.json --workspace .` |
| "Run a configured lens" | `cartograph lens --graph cartograph-out/graph.json --name <lens-name> --params '{...}'` |
| "Show me the gaps" | `jq '.meta.unresolved' cartograph-out/graph.json` |
| "Service inventory" | `cartograph coverage --graph cartograph-out/graph.json` |

## When to re-index

Re-index after:
- Source code changes that add/move/delete endpoints, message handlers, or HTTP calls
- Adding or modifying lens definitions in `.cartograph/lenses/`
- Editing `service-registry.yaml` or `resolve-hints.json`
- Adding or removing services (new directory with `cartograph.yaml`)

You don't need to re-index after:
- Pure logic changes inside an already-indexed handler
- Documentation/comment edits
- Configuration changes that don't affect topology (logging, feature flags)

## Reading the graph directly

The graph is plain JSON. For scripted analysis:

```python
import json
graph = json.loads(open("cartograph-out/graph.json").read())

# Every node, edge, and gap is here:
graph["nodes"]               # list of node dicts
graph["edges"]               # list of edge dicts
graph["meta"]["services"]    # discovered services
graph["meta"]["unresolved"]  # what the linker couldn't close
graph["meta"]["schema"]      # field schemas per label
```

The query module mirrors the CLI:

```python
from cartograph.query import flow, search, cross_service_edges, kafka_topics, find_callers
result = flow(graph, "/api/orders")
```

## Verification

```bash
# Check graph against an expectations file
cartograph verify --graph cartograph-out/graph.json --suite fixtures/expectations/my-suite.yaml
```

Expectations files declare required endpoints, edges, and node counts. Use them in CI to catch indexing regressions.

## MCP / JSON-lines mode

For agent integration:

```bash
cartograph serve --graph cartograph-out/graph.json
```

This starts a JSON-lines stdin/stdout server supporting `tools/list` and `tools/call` methods — every query function is exposed.
