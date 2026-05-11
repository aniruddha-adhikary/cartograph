import json
import subprocess
import sys
from pathlib import Path

from conftest import FIXTURES, PACKS


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "codette", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_index_writes_graph(tmp_path):
    out = tmp_path / "g.json"
    result = _run_cli(
        "index",
        "--repo", str(FIXTURES / "crosstier-mini"),
        "--packs", str(PACKS),
        "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    graph = json.loads(out.read_text())
    assert len(graph["nodes"]) > 0
    assert any(e["type"] == "CROSSES_TIER" for e in graph["edges"])


def test_cli_changed_files_flag(tmp_path):
    out = tmp_path / "g.json"
    # First full index
    r1 = _run_cli(
        "index", "--repo", str(FIXTURES / "express-mini"),
        "--packs", str(PACKS), "--out", str(out),
    )
    assert r1.returncode == 0, r1.stderr
    g1 = json.loads(out.read_text())
    n1 = len(g1["nodes"])
    # Re-run incrementally with no actual changes (file content same) → same graph
    r2 = _run_cli(
        "index", "--repo", str(FIXTURES / "express-mini"),
        "--packs", str(PACKS), "--out", str(out),
        "--changed-files", "server.js",
    )
    assert r2.returncode == 0, r2.stderr
    g2 = json.loads(out.read_text())
    assert len(g2["nodes"]) == n1


def test_cli_version_pin_mismatch_fails(tmp_path):
    out = tmp_path / "g.json"
    r = _run_cli(
        "index", "--repo", str(FIXTURES / "react-mini"),
        "--packs", str(PACKS), "--out", str(out),
        "--engine-version-pin", "9.9.9",
    )
    assert r.returncode == 2
    assert "engine version mismatch" in r.stderr
