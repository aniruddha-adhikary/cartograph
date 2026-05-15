# Cartograph Agent Instructions

Use Cartograph before broad source search when a question involves service boundaries, endpoints, message topics, database access paths, ownership slices, or cross-repo flow.

## Workflow

1. If `cartograph-out/GRAPH_REPORT.md` exists, read it before answering architecture or flow questions.
2. Run `cartograph tools` to inspect the available CLI surface.
3. Prefer graph queries before raw text search:
   - `cartograph flow --graph cartograph-out/graph.json --anchor <anchor>`
   - `cartograph explain --graph cartograph-out/graph.json --anchor <anchor>`
   - `cartograph search --graph cartograph-out/graph.json --query <terms>`
   - `cartograph lens list --graph cartograph-out/graph.json --workspace .`
   - `cartograph lens --graph cartograph-out/graph.json --name <lens> --workspace . --params '<json>'`
4. Read source files when editing code or validating exact implementation details.
5. After service-code changes, refresh the graph:

```bash
cartograph index --workspace . --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md
```

## Lens Rules

- Project lenses live in `.cartograph/lenses/*.json`.
- Author lenses as raw Kuzu-style Cypher query specs with `kind: "query"`.
- Do not create a Cartograph-specific mini-language for project lenses.
- Run `cartograph lens list` before adding a new lens.
- Use declared `returns` as the type contract for returned node labels and relationship types.

Example:

```json
{
  "project.checkout-db-flow": {
    "kind": "query",
    "language": "kuzu-cypher",
    "returns": {
      "call": "HttpCall",
      "edge": "CROSSES_TIER",
      "route": "Endpoint"
    },
    "query": [
      "MATCH (call:HttpCall)-[edge:CROSSES_TIER]->(route:Endpoint)",
      "WHERE route.path CONTAINS $path",
      "RETURN call, edge, route"
    ]
  }
}
```
