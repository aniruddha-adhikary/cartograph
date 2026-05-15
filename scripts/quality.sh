#!/usr/bin/env bash
set -euo pipefail

python -m ruff format --check .
python -m ruff check .
python -m compileall cartograph

if python -c "import mypy" >/dev/null 2>&1; then
  python -m mypy
else
  echo "mypy is not installed; install with: python -m pip install -e '.[dev]'" >&2
  exit 1
fi

python -m pytest -q
