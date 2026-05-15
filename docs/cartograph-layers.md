# Cartograph Layers

Cartograph core is intentionally small: it reads files, emits graph primitives, merges service graphs, and runs configured interpretations. Project meaning belongs in layers.

## Layer Types

**Pack overlays** live in `.cartograph/packs/*.json`. They define extraction vocabulary: annotations, route tokens, producer methods, consumer annotations, and client-call tokens. They do not execute code.

**View overlays** live in `.cartograph/views/*.json`. They define named graph queries such as `endpoints`, `kafka-topics`, ownership views, compliance boundaries, or any project-specific projection that can be expressed as filters and grouping.

**Lens overlays** live in `.cartograph/lenses/*.json`. They define named raw Kuzu Cypher projections for project, domain, or task concepts.

**Plugins** live in `.cartograph/plugins/*.py`. They are explicit local Python projections with `run(graph, args)`. They execute only through `cartograph run-plugin --allow-plugin`.

## Composition

Layers are applied in order:

```bash
cartograph index \
  --workspace . \
  --layer-dir .cartograph \
  --layer-dir ../team-cartograph-layer \
  --out cartograph-out/graph.json

cartograph query \
  --graph cartograph-out/graph.json \
  --name service-risk \
  --layer-dir .cartograph \
  --layer-dir ../team-cartograph-layer

cartograph lens \
  --graph cartograph-out/graph.json \
  --name project.checkout-db-flow \
  --workspace . \
  --layer-dir ../team-cartograph-layer
```

The project `.cartograph` directory is the first layer. Explicit `--layer-dir` entries are applied after it in command-line order, so later layers can override earlier lens/view names or pack sections. Pack dictionaries merge deeply, token lists append unique values, and named object lists such as `message_buses` merge by `name`.

## Lens Queries

A coding agent can add a project lens when a task uses repository-specific language that the generated graph does not know yet. The lens is a raw Kuzu Cypher query, not a Cartograph-specific operator DSL:

```json
{
  "project.checkout-db-flow": {
    "kind": "query",
    "language": "kuzu-cypher",
    "returns": {
      "call": "HttpCall",
      "edge": "CROSSES_TIER",
      "route": "Endpoint",
      "lens": "Lens"
    },
    "query": [
      "MATCH (call:HttpCall)-[edge:CROSSES_TIER]->(route:Endpoint)",
      "OPTIONAL MATCH (lens:Lens)-[contains:CONTAINS]->(route:Endpoint)",
      "WHERE route.path CONTAINS 'checkout'",
      "RETURN call, edge, route, lens"
    ]
  }
}
```

This keeps abstraction open-ended: a query can bind any combination of code nodes, framework mappings, route files, generated `Lens` nodes, runtime traces, topics, SQL mappers, or database tables once those labels and relationships exist in the graph schema.

## LLM Workflow

When Cartograph misses a project convention, an LLM should not edit Cartograph core. It should:

1. Run `cartograph discover-packs --workspace . --out .cartograph/discovery.json`.
2. Inspect representative source files.
3. Add or edit `.cartograph/packs/*.json` for deterministic extraction vocabulary, including named `message_buses` for Kafka, internal event buses, queue abstractions, or project-specific topic systems.
4. Add `.cartograph/lenses/*.json` for task-specific or domain-specific graph projections.
5. Add `.cartograph/views/*.json` for project-specific tabular/list questions.
6. Use `.cartograph/plugins/*.py` only when declarative lenses and views are insufficient.
7. Re-run `cartograph index` and the project verifier.

M1 uses only reviewed deterministic layers. M1.5 may propose layers from LLM extraction, but promotion to pack/lens/view config is an explicit review step.
