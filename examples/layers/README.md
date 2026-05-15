# Cartograph Interpretation Layers

Cartograph core owns graph primitives. Project interpretation is layered on top.

Layer directories can contain:

- `packs/*.json` — extraction vocabulary overlays
- `lenses/*.json` — named graph projections for project/domain/task concepts
- `views/*.json` — named graph queries
- `plugins/*.py` — explicit local Python projections with `run(graph, args)`

Example:

```bash
cartograph index \
  --workspace . \
  --layer-dir examples/layers/team-default \
  --layer-dir examples/layers/project-overrides \
  --out cartograph-out/graph.json

cartograph query \
  --graph cartograph-out/graph.json \
  --name medium-confidence-crossings \
  --layer-dir examples/layers/team-default \
  --layer-dir examples/layers/project-overrides

cartograph lens \
  --graph cartograph-out/graph.json \
  --name project.checkout-db-flow \
  --layer-dir examples/layers/project-overrides

cartograph run-plugin \
  --allow-plugin \
  --graph cartograph-out/graph.json \
  --plugin examples/layers/project-overrides/plugins/service_risk.py
```

An LLM should add or modify files in a project layer. It should not patch Cartograph core for project-specific framework semantics or query interpretation.
