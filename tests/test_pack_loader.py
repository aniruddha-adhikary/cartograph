from pathlib import Path

import pytest

from codette.pack import PackError, load_pack, load_packs


def _write(tmp_path: Path, rel: str, text: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_load_real_packs():
    here = Path(__file__).resolve().parent.parent
    packs = load_packs(here / "packs")
    names = {p.name for p in packs}
    assert {"spring", "express", "react"} <= names
    for p in packs:
        for rule in p.rules:
            assert rule.id
            assert rule.language in {
                "java", "javascript", "typescript", "tsx",
                "python", "go", "c_sharp",
            }
            # query compiled successfully (cached on rule)
            assert rule._query is not None


def test_missing_id_rejected(tmp_path):
    p = _write(tmp_path, "x/a.yaml", "when: {language: java}\nmatch: {query: '(identifier) @x'}\nemit: []")
    with pytest.raises(PackError, match="missing key 'id'"):
        load_pack(p)


def test_unsupported_language_rejected(tmp_path):
    p = _write(tmp_path, "x/a.yaml", """
id: x.bad
when: {language: cobol}
match: {query: '(identifier) @x'}
emit:
  - node: {label: X, id: 'x'}
""")
    with pytest.raises(PackError, match="unsupported language"):
        load_pack(p)


def test_bad_query_rejected_at_load(tmp_path):
    p = _write(tmp_path, "x/a.yaml", """
id: x.bad
when: {language: java}
match: {query: '(this is not a valid query'}
emit:
  - node: {label: X, id: 'x'}
""")
    with pytest.raises(PackError, match="query compile failed"):
        load_pack(p)


def test_emit_must_be_list(tmp_path):
    p = _write(tmp_path, "x/a.yaml", """
id: x.bad
when: {language: java}
match: {query: '(identifier) @x'}
emit: not-a-list
""")
    with pytest.raises(PackError, match="emit must be a list"):
        load_pack(p)


def test_node_requires_label_and_id(tmp_path):
    p = _write(tmp_path, "x/a.yaml", """
id: x.bad
when: {language: java}
match: {query: '(identifier) @x'}
emit:
  - node: {}
""")
    with pytest.raises(PackError, match="missing 'label'"):
        load_pack(p)


def test_multi_doc_yaml(tmp_path):
    p = _write(tmp_path, "x/a.yaml", """
id: x.one
when: {language: java}
match: {query: '(identifier) @x'}
emit:
  - node: {label: X, id: 'x'}
---
id: x.two
when: {language: java}
match: {query: '(identifier) @y'}
emit:
  - node: {label: Y, id: 'y'}
""")
    pack = load_pack(p)
    assert [r.id for r in pack.rules] == ["x.one", "x.two"]
