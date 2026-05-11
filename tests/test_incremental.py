import shutil
from pathlib import Path

from codette.engine import Engine
from conftest import FIXTURES, PACKS


def _copy_repo(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst)


def test_changed_file_only_redoes_that_file(tmp_path):
    repo = tmp_path / "crosstier"
    _copy_repo(FIXTURES / "crosstier-mini", repo)

    engine = Engine.from_packs(PACKS)
    g1, _ = engine.index(repo)
    ct_before = sum(1 for e in g1.edges if e.type == "CROSSES_TIER")
    assert ct_before == 2

    # Add a new endpoint on backend
    server = repo / "backend" / "server.js"
    text = server.read_text()
    text = text.replace(
        "app.listen(3000);",
        "app.put('/api/users/:id', (req, res) => res.json({}));\napp.listen(3000);",
    )
    server.write_text(text)

    g2, _ = engine.index(
        repo,
        changed_files=["backend/server.js"],
        existing_graph=g1,
    )
    server_endpoints = [
        n for n in g2.by_label("Endpoint")
        if n.properties["file"] == "backend/server.js"
    ]
    methods = sorted(e.properties["http_method"] for e in server_endpoints)
    assert methods == ["GET", "POST", "PUT"]

    # Frontend nodes untouched
    frontend = [
        n for n in g2.nodes
        if n.properties.get("file", "").startswith("frontend/")
    ]
    assert len(frontend) >= 1


def test_changed_file_drops_stale_nodes(tmp_path):
    repo = tmp_path / "express"
    _copy_repo(FIXTURES / "express-mini", repo)

    engine = Engine.from_packs(PACKS)
    g1, _ = engine.index(repo)
    nodes_before = {n.id for n in g1.by_label("Endpoint")}
    assert len(nodes_before) >= 4

    # Empty the file → no endpoints should remain from it
    (repo / "server.js").write_text("// emptied\n")
    g2, _ = engine.index(repo, changed_files=["server.js"], existing_graph=g1)
    remaining = [n for n in g2.by_label("Endpoint") if n.properties["file"] == "server.js"]
    assert remaining == []
