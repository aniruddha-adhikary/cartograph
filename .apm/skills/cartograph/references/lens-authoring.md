# Cartograph Lens Authoring

Project lenses live in `.cartograph/lenses/*.json`. Author them as raw Kuzu-style Cypher query specs, not a Cartograph-specific operator DSL.

Before adding a lens:

```bash
cartograph lens list --graph cartograph-out/graph.json --workspace .
```

Lens shape:

```json
{
  "project.example-flow": {
    "kind": "query",
    "language": "kuzu-cypher",
    "returns": {
      "caller": "HttpCall",
      "edge": "CROSSES_TIER",
      "target": "Endpoint"
    },
    "query": [
      "MATCH (caller:HttpCall)-[edge:CROSSES_TIER]->(target:Endpoint)",
      "WHERE target.path CONTAINS $path",
      "RETURN caller, edge, target"
    ]
  }
}
```

Rules:

- Use `kind: "query"` and `language: "kuzu-cypher"`.
- Use `returns` as the type contract for returned node labels and relationship types.
- Use `$param` placeholders and pass values through `--params`.
- Use `OPTIONAL MATCH` for nullable relationships, such as route -> mapper -> SQL -> table chains.
- Keep project-specific concepts in project lens files; do not patch Cartograph core for one repository's vocabulary.
- Run `bash scripts/quality.sh` after adding lens examples or tests.

Run a lens:

```bash
cartograph lens \
  --graph cartograph-out/graph.json \
  --name project.example-flow \
  --workspace . \
  --params '{"path":"checkout"}'
```
