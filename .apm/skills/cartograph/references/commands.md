# Cartograph Command Guide

Use these mappings before falling back to broad text search.

| User asks | Start with |
|---|---|
| "What happens when X runs?" | `cartograph explain --graph cartograph-out/graph.json --anchor <X>` |
| "Show the flow for X" | `cartograph flow --graph cartograph-out/graph.json --anchor <X>` |
| "Who calls X?" | `cartograph find-callers --graph cartograph-out/graph.json --symbol <X>` |
| "What does X call?" | `cartograph find-callees --graph cartograph-out/graph.json --symbol <X>` |
| "What endpoints does service S expose?" | `cartograph endpoints-in-service --graph cartograph-out/graph.json --service <S>` |
| "Which topics/events reach S?" | `cartograph kafka-topics --graph cartograph-out/graph.json --consumer-service <S>` |
| "Show cross-service calls from S" | `cartograph cross-service-edges --graph cartograph-out/graph.json --from-service <S>` |
| "Where should I edit?" | `cartograph search --graph cartograph-out/graph.json --query <terms>` |
| "What project lenses exist?" | `cartograph lens list --graph cartograph-out/graph.json --workspace .` |

Quality gate before finishing code changes:

```bash
bash scripts/quality.sh
```

Graph refresh after service-code changes:

```bash
cartograph index --workspace . --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md
```
