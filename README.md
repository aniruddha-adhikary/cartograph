# codette

Polyglot tree-sitter extractor engine with YAML-driven framework packs.
Indexes a source repository into a typed property graph (nodes + edges)
and cross-links HTTP calls between frontend and backend tiers.

This is Stage 1 of the roadmap: engine core plus three starter packs
(Spring / Express / React) wired end-to-end so the cross-tier linker is
provable on a real fixture.

## Install

Requires Python 3.12+.

```bash
pip install -e .[dev]
```

## CLI

```bash
codette index \
    --repo <path/to/repo> \
    --packs <path/to/packs> \
    --out  <out/graph.json> \
    [--changed-files file1,file2] \
    [--engine-version-pin 0.1.0]
```

The CLI writes a deterministic JSON graph to `--out` and a per-pack metrics
JSON payload to stderr.

## Quick demo

```bash
codette index \
    --repo tests/fixtures/crosstier-mini \
    --packs packs \
    --out /tmp/g.json
jq '.edges[] | select(.type=="CROSSES_TIER")' /tmp/g.json
```

The fixture contains an Express backend (`GET /api/users`, `POST /api/users`)
and a React frontend that calls them via `fetch()`. The HTTP linker emits
two `CROSSES_TIER` edges.

## Programmatic API

```python
from codette import Engine

engine = Engine.from_packs("packs/")
graph, report = engine.index("/path/to/repo")
graph.to_json("out/graph.json")
```

## Layout

```
src/codette/        engine + linkers
packs/              YAML rule packs (spring, express, react)
tests/              unit + snapshot tests
docs/schema.md      output graph JSON schema
```

See `docs/schema.md` for the output format.

## Tests

```bash
pytest -q
# refresh snapshots after intentional pack changes:
CODETTE_UPDATE_SNAPSHOTS=1 pytest -q
```
