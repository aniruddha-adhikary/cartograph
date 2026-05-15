---
name: cartograph
description: "Build and query a deterministic polyrepo service graph. Use for Java/Spring, Kafka, REST, WebClient, Eureka, endpoint, and cross-service flow questions."
trigger: /cartograph
---

# /cartograph

Cartograph builds and queries a configurable graph for service-oriented codebases. Use it Graphify-style: CLI first, optional JSON-lines server when a long-running tool bridge is useful.

## Commands

```bash
cartograph index --workspace . --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md
cartograph tools
cartograph discover-packs --workspace . --out .cartograph/discovery.json
cartograph index --workspace . --packs-dir .cartograph/packs --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md
cartograph verify --graph cartograph-out/graph.json --suite fixtures/expectations/m1-real-java.yaml
cartograph flow --graph cartograph-out/graph.json --anchor "/api/permits/motor-vehicle"
cartograph search --graph cartograph-out/graph.json --query "motor vehicle permit"
cartograph endpoints-in-service --graph cartograph-out/graph.json --service permits-api
cartograph cross-service-edges --graph cartograph-out/graph.json --from-service web
cartograph kafka-topics --graph cartograph-out/graph.json --consumer-service inspections-api
cartograph coverage-report --graph cartograph-out/graph.json
cartograph explain --graph cartograph-out/graph.json --anchor "/api/permits/motor-vehicle"
cartograph lens --graph cartograph-out/graph.json --name domain.permits
cartograph lens list --graph cartograph-out/graph.json --workspace .
cartograph lens --graph cartograph-out/graph.json --name project.checkout-db-flow --workspace .
cartograph query --graph cartograph-out/graph.json --name endpoints
cartograph query --graph cartograph-out/graph.json --name endpoints --param service=permits-api
cartograph query --graph cartograph-out/graph.json --name cross-service-edges
cartograph query --graph cartograph-out/graph.json --name kafka-topics
cartograph query --graph cartograph-out/graph.json --name my-project-view --views-dir .cartograph/views
cartograph run-plugin --allow-plugin --graph cartograph-out/graph.json --plugin .cartograph/plugins/my_view.py --args '{"limit": 10}'
cartograph serve --graph cartograph-out/graph.json
```

## Agent Rules

- Before broad source search for service-flow questions, read `cartograph-out/GRAPH_REPORT.md` if it exists.
- Prefer purpose-built CLI tools (`flow`, `search`, `endpoints-in-service`, `cross-service-edges`, `kafka-topics`, `coverage-report`, `lens`) for endpoint, message, and cross-service questions.
- If asked "what happens when X runs?", start with `cartograph explain --graph cartograph-out/graph.json --anchor <X>`.
- If asked "who calls X?", start with `cartograph find-callers --graph cartograph-out/graph.json --symbol <X>`.
- If asked "what does service S expose?", start with `cartograph endpoints-in-service --graph cartograph-out/graph.json --service <S>`.
- If asked "which topics/events reach S?", start with `cartograph kafka-topics --graph cartograph-out/graph.json --consumer-service <S>`.
- If asked "where should I edit?", start with `cartograph search --graph cartograph-out/graph.json --query <terms>`.
- Lenses are raw Kuzu Cypher projections, not a Cartograph-specific operator DSL. If the task has a domain concept like "checkout risk", "tenant onboarding", or "claims adjudication", create `.cartograph/lenses/<name>.json` with `kind: "query"` and run `cartograph lens --workspace . --name <lens>`.
- Run `cartograph lens list --graph cartograph-out/graph.json --workspace .` before creating a new lens; reuse or refine an existing lens when it already answers the question.
- Express higher-level abstraction directly in Kuzu-style Cypher with `MATCH`, shared variables, `WHERE`, and `RETURN`; do not invent `union`/`expand`/`pipeline` lens specs.
- Use configured views through `cartograph query --name <view>` when a project has added `.cartograph/views/*.json`.
- Read source files when making edits or validating exact implementation details.
- After modifying service code, refresh the graph with `cartograph index`.
- If a project uses framework wrappers Cartograph misses, run `cartograph discover-packs`; use the discovery JSON to create `.cartograph/packs/*.json` overlays instead of editing extractor code.
- If a project needs a custom concept lens, create `.cartograph/lenses/<name>.json`; if it needs a custom tabular/list query like "topics for another bus", create `.cartograph/views/<name>.json` and run it with `cartograph query --name <name>`.
- If a view cannot express the logic, create an explicit local plugin under `.cartograph/plugins/<name>.py` with `run(graph, args)`, review it, and execute it with `cartograph run-plugin --allow-plugin`; do not hide project-specific behavior in Cartograph core.

## Lens Specs

```json
{
  "project.checkout-db-flow": {
    "kind": "query",
    "language": "kuzu-cypher",
    "returns": {
      "route": "Endpoint",
      "call": "CROSSES_TIER",
      "target": "Endpoint",
      "sql": "SqlQuery"
    },
    "query": [
      "MATCH (call:HttpCall)-[edge:CROSSES_TIER]->(route:Endpoint)",
      "OPTIONAL MATCH (route:Endpoint)-[uses:USES]->(sql:SqlQuery)",
      "WHERE route.path CONTAINS 'checkout'",
      "RETURN call, edge, route, uses, sql"
    ]
  }
}
```

## Python API

```python
from pathlib import Path
from cartograph.indexer import index_workspace
from cartograph.report import render_report
from cartograph.query import flow

graph = index_workspace(Path("."))
report = render_report(graph.to_dict())
trace = flow(graph.to_dict(), "/api/permits/motor-vehicle")
```
