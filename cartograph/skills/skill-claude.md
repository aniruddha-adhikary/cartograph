---
name: cartograph
description: "Build and query a deterministic polyrepo service graph for Spring, Kafka, REST, WebClient, Eureka, and cross-service flow questions."
---

# cartograph

Use Cartograph when the task depends on service boundaries, endpoints, Kafka topics, or cross-repo call paths. Use it Graphify-style: CLI first, optional JSON-lines server when a long-running tool bridge is useful.

```bash
cartograph index --workspace . --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md
cartograph tools
cartograph discover-packs --workspace . --out .cartograph/discovery.json
cartograph index --workspace . --packs-dir .cartograph/packs --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md
cartograph flow --graph cartograph-out/graph.json --anchor "<endpoint-or-node>"
cartograph search --graph cartograph-out/graph.json --query "<query>"
cartograph endpoints-in-service --graph cartograph-out/graph.json --service <service>
cartograph cross-service-edges --graph cartograph-out/graph.json --from-service <service>
cartograph kafka-topics --graph cartograph-out/graph.json --consumer-service <service>
cartograph coverage-report --graph cartograph-out/graph.json
cartograph explain --graph cartograph-out/graph.json --anchor "<endpoint-or-node>"
cartograph lens --graph cartograph-out/graph.json --name domain.<name>
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

Read `cartograph-out/GRAPH_REPORT.md` before answering broad architecture questions. If asked "what happens when X runs?", start with `cartograph explain`. If asked "who calls X?", start with `cartograph find-callers`. If asked "what does service S expose?", start with `cartograph endpoints-in-service`. If asked "which topics/events reach S?", start with `cartograph kafka-topics`. Use source reads for exact edits and debugging. For missing framework patterns, generate `.cartograph/packs/*.json` overlays from discovery output rather than changing Cartograph code. Lenses are raw Kuzu Cypher projections, not a Cartograph-specific operator DSL: create `.cartograph/lenses/*.json` with `kind: "query"` for domain concepts like checkout, tenant onboarding, or claims adjudication. Run `cartograph lens list --graph cartograph-out/graph.json --workspace .` before creating a new lens. Express abstraction directly with `MATCH`, shared variables, `WHERE`, and `RETURN`. For project-specific queries, generate `.cartograph/lenses/*.json`, `.cartograph/views/*.json`, or explicit `.cartograph/plugins/*.py` files and run them with `cartograph lens`, `cartograph query --name <view>`, or reviewed `cartograph run-plugin --allow-plugin`.

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
