from codette.ids import stable_node_id


def test_id_is_deterministic():
    a = stable_node_id("r", "f.py", "class Foo:\n    pass", 10)
    b = stable_node_id("r", "f.py", "class Foo:\n    pass", 10)
    assert a == b
    assert len(a) == 16


def test_id_whitespace_normalized():
    a = stable_node_id("r", "f.py", "class Foo: pass", 10)
    b = stable_node_id("r", "f.py", "class   Foo:\tpass", 10)
    assert a == b


def test_id_changes_with_rule_id():
    a = stable_node_id("rule.one", "f.py", "x", 1)
    b = stable_node_id("rule.two", "f.py", "x", 1)
    assert a != b


def test_id_changes_with_line():
    a = stable_node_id("r", "f.py", "x", 1)
    b = stable_node_id("r", "f.py", "x", 2)
    assert a != b


def test_id_changes_with_file():
    a = stable_node_id("r", "a.py", "x", 1)
    b = stable_node_id("r", "b.py", "x", 1)
    assert a != b
