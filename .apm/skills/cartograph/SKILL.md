---
name: cartograph
description: "Use Cartograph when a coding task involves service boundaries, endpoints, Kafka/message topics, cross-repo flows, graph lenses, Kuzu-style lens authoring, database access paths, runtime traces, or deciding where to edit in a polyrepo. Prefer Cartograph CLI queries before broad source search, then read source files for exact edits."
---

# Cartograph

Use Cartograph as the graph-first navigation layer for codebases. The default workflow is:

1. Read `cartograph-out/GRAPH_REPORT.md` if it exists and the task is architectural or flow-related.
2. Run `cartograph tools` to confirm the local command surface.
3. Query the graph before broad source search.
4. Read source files to verify exact implementation details before editing.
5. Refresh the graph after service-code changes.

## Core Commands

```bash
cartograph tools
cartograph flow --graph cartograph-out/graph.json --anchor "<endpoint-or-node>"
cartograph explain --graph cartograph-out/graph.json --anchor "<endpoint-or-node>"
cartograph search --graph cartograph-out/graph.json --query "<query>"
cartograph lens list --graph cartograph-out/graph.json --workspace .
cartograph lens --graph cartograph-out/graph.json --name <lens> --workspace . --params '{"key":"value"}'
```

Use `cartograph index --workspace . --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md` after code changes.

## References

- For task-to-command mapping, read [references/commands.md](references/commands.md).
- For authoring `.cartograph/lenses/*.json`, read [references/lens-authoring.md](references/lens-authoring.md).
- For project extension choices, read [references/project-layers.md](references/project-layers.md).
