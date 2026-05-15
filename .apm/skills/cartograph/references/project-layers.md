# Project Layers & Overrides

Cartograph supports a small, layered configuration model. Use the smallest extension surface that fits your task.

## What goes where

| Need | File | Scope |
|---|---|---|
| Mark a directory as a service | `<service>/cartograph.yaml` | One service |
| Exclude generated/test paths in a service | `<service>/cartograph.yaml` `exclude:` | One service |
| Map hostnames to service names | `service-registry.yaml` (workspace root) | Workspace |
| One-off node patches | `resolve-hints.json` (workspace root) | Workspace |
| Add a framework extractor | `.cartograph/lenses/*.json` (`scope: source`) | Workspace |
| Parse raw fields into structured ones | `.cartograph/lenses/*.json` (`scope: resolve`) | Workspace |
| Named graph queries | `.cartograph/lenses/*.json` (`scope: graph`) | Workspace |
| Team-shared overrides | `--layer-dir <path>` passed to `cartograph index` | Per-invocation |
| Local-only executable analysis | `.cartograph/plugins/*.py` + `cartograph run-plugin --allow-plugin` | Workspace |

## `cartograph.yaml` per service

```yaml
name: orders-service
include_test_paths: false
exclude:
  - src/generated/**
  - "**/legacy/**"
metadata:
  owner: payments-team
```

`name` overrides the directory name. `exclude` extends the workspace-wide ignore patterns. `metadata` is free-form — useful for filtering with graph queries later.

## Lens precedence

When `cartograph index` runs:
1. Load built-in lenses (`cartograph/lens_defs/*.json`)
2. Load project lenses (`.cartograph/lenses/*.json` if `--lens-dir` points there)
3. Load team/layer lenses (any `--layer-dir`s)

A lens with the same `name` as one already loaded **overrides** it. Use this to customise a built-in. A lens with a new name **extends** the set.

Run `cartograph lens list` to see what's active.

## When to use a plugin instead of a lens

Plugins are local Python scripts. Use them only when:
- The analysis needs imperative logic that lenses can't express (graph traversal, statistical analysis, ML)
- The output is a one-off report rather than nodes/edges that belong in the graph itself

```bash
cartograph run-plugin --graph cartograph-out/graph.json --plugin scripts/find_orphan_endpoints.py --allow-plugin
```

If you find yourself reaching for a plugin to extract data from source files, write a `source` lens instead — extraction belongs in the lens system so it composes with everything else.

## What's *not* supported (anymore)

The old `cartograph/packs/*.json` system from M1 has been removed. There is no `discover-packs` command and no `--packs-dir` flag. Everything that used to live in packs is now expressed as `source` lenses in `.cartograph/lenses/`. Project lenses extend and override built-in lenses by name.

If you encounter old documentation referencing packs, the lens system is the replacement — the mapping is direct: each pack's `controller_annotations` / `producer_methods` / `listener_annotation` etc. becomes the `match` config of a `source` lens.
