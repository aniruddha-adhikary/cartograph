#!/usr/bin/env bash
set -euo pipefail

python scripts/prepare_real_repos.py
python -m cartograph index \
  --workspace .cartograph-real-repos/workspace \
  --out cartograph-out/real-repos.graph.json \
  --report cartograph-out/GRAPH_REPORT.md
python -m cartograph verify \
  --graph cartograph-out/real-repos.graph.json \
  --suite fixtures/expectations/m1-real-java.yaml
