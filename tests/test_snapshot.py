"""Snapshot tests: regression on the full graph JSON per fixture.

Run with `CODETTE_UPDATE_SNAPSHOTS=1 pytest` to refresh after intentional changes.
"""
import json
import os
from pathlib import Path

import pytest

from codette.engine import Engine
from conftest import FIXTURES, PACKS, SNAPSHOTS

UPDATE = os.environ.get("CODETTE_UPDATE_SNAPSHOTS") == "1"


def _redact(graph_dict: dict) -> dict:
    """Strip version-sensitive fields so snapshots don't churn on version bumps."""
    out = json.loads(json.dumps(graph_dict))  # deep copy
    for n in out["nodes"]:
        prov = n["properties"].get("provenance")
        if prov:
            prov.pop("engine_version", None)
    for e in out["edges"]:
        prov = e["properties"].get("provenance")
        if prov:
            prov.pop("engine_version", None)
    return out


@pytest.mark.parametrize("fixture", ["spring-mini", "express-mini", "react-mini", "crosstier-mini"])
def test_fixture_snapshot(fixture):
    engine = Engine.from_packs(PACKS)
    graph, _ = engine.index(FIXTURES / fixture)
    actual = _redact(graph.to_dict())

    snapshot_path = SNAPSHOTS / f"{fixture}.json"
    if UPDATE or not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(actual, indent=2) + "\n")
        if not UPDATE:
            pytest.skip(f"created snapshot {snapshot_path}")

    expected = json.loads(snapshot_path.read_text())
    assert actual == expected, (
        f"snapshot drift for {fixture}; re-run with CODETTE_UPDATE_SNAPSHOTS=1 to refresh"
    )
