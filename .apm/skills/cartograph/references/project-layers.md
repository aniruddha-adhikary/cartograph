# Cartograph Project Layers

Choose the smallest extension surface that fits the task.

| Need | Use |
|---|---|
| Add framework annotations, route tokens, client tokens, or message bus vocabulary | `.cartograph/packs/*.json` |
| Add a typed graph projection across code concepts | `.cartograph/lenses/*.json` |
| Add a simple list/group query | `.cartograph/views/*.json` |
| Add project-local executable analysis logic | `.cartograph/plugins/*.py` with `cartograph run-plugin --allow-plugin` |

Discovery loop for missing framework conventions:

```bash
cartograph discover-packs --workspace . --out .cartograph/discovery.json
```

Then inspect representative source files and add reviewed pack overlays. Do not use unreviewed LLM output as production extraction config.

Layered index command:

```bash
cartograph index \
  --workspace . \
  --layer-dir .cartograph \
  --out cartograph-out/graph.json \
  --report cartograph-out/GRAPH_REPORT.md
```
