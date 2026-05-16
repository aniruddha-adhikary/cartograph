"""Tests for A2/A3/A4 enhancements to run_resolve_lenses."""
from __future__ import annotations

from cartograph.graph import Graph
from cartograph.lens_runner import run_resolve_lenses


def _make_node(label: str, **props) -> dict:
    base = {
        "id": f"svc:f.java:1:abcd",
        "label": label,
        "service": "svc",
        "file": "f.java",
        "line": 1,
        "source": "lens:test",
        "confidence": "high",
    }
    base.update(props)
    return base


def test_a2_resolve_template_fallback_chain():
    """A2: when the first capture is missing, fall back to the next; literal default supported."""
    graph = Graph()
    graph.nodes.append(_make_node("CacheOp", args_text='value = "users"'))
    lenses = [{
        "name": "test-fallback",
        "scope": "resolve",
        "match": {
            "label": "CacheOp",
            "from": "args_text",
            "patterns": [{"regex": r'value\s*=\s*"(?P<v>[^"]+)"'}],
        },
        "set": {"cache": "{{a|v|fallback-lit}}"},
    }]
    n = run_resolve_lenses(lenses, graph)
    assert n == 1
    assert graph.nodes[0]["cache"] == "users"


def test_a2_literal_default_when_no_capture_matches():
    graph = Graph()
    graph.nodes.append(_make_node("X", raw="something"))
    lenses = [{
        "name": "lit",
        "scope": "resolve",
        "match": {
            "label": "X",
            "from": "raw",
            "patterns": [{"regex": r"(?P<a>some)"}],
        },
        "set": {"kind": "{{missing|literal-default}}"},
    }]
    run_resolve_lenses(lenses, graph)
    assert graph.nodes[0]["kind"] == "literal-default"


def test_a3_per_key_skip_writes_independent_keys():
    """A3: x already set, y empty — y still gets written."""
    graph = Graph()
    graph.nodes.append(_make_node(
        "Cfg", raw='profile="prod" env="qa"', x="already-set",
    ))
    lenses = [{
        "name": "two-keys",
        "scope": "resolve",
        "match": {
            "label": "Cfg",
            "from": "raw",
            "patterns": [{"regex": r'profile="(?P<p>[^"]+)"\s+env="(?P<e>[^"]+)"'}],
        },
        "set": {"x": "{{p}}", "y": "{{e}}"},
    }]
    n = run_resolve_lenses(lenses, graph)
    assert n == 1
    assert graph.nodes[0]["x"] == "already-set"  # not overwritten
    assert graph.nodes[0]["y"] == "qa"           # newly written


def test_a3_skip_entirely_if_all_keys_already_set():
    graph = Graph()
    graph.nodes.append(_make_node("Cfg", raw="data", x="x1", y="y1"))
    lenses = [{
        "name": "noop",
        "scope": "resolve",
        "match": {
            "label": "Cfg",
            "from": "raw",
            "patterns": [{"regex": r"(?P<v>data)"}],
        },
        "set": {"x": "{{v}}", "y": "{{v}}"},
    }]
    n = run_resolve_lenses(lenses, graph)
    assert n == 0
    assert graph.nodes[0]["x"] == "x1"
    assert graph.nodes[0]["y"] == "y1"


def test_a4_where_filter_matches_only_correct_kind():
    """A4: where: {kind: "k1"} only fires on matching nodes."""
    graph = Graph()
    graph.nodes.append(_make_node("Svc", kind="k1", raw="op=hello"))
    graph.nodes.append(_make_node("Svc", kind="k2", raw="op=hello"))
    lenses = [{
        "name": "kind-only",
        "scope": "resolve",
        "match": {
            "label": "Svc",
            "where": {"kind": "k1"},
            "from": "raw",
            "patterns": [{"regex": r"op=(?P<o>\w+)"}],
        },
        "set": {"op": "{{o}}"},
    }]
    n = run_resolve_lenses(lenses, graph)
    assert n == 1
    assert graph.nodes[0]["op"] == "hello"
    assert "op" not in graph.nodes[1]


def test_a4_where_multiple_keys_anded():
    graph = Graph()
    graph.nodes.append(_make_node("Svc", kind="k1", framework="f1", raw="v=1"))
    graph.nodes.append(_make_node("Svc", kind="k1", framework="f2", raw="v=2"))
    lenses = [{
        "name": "two-where",
        "scope": "resolve",
        "match": {
            "label": "Svc",
            "where": {"kind": "k1", "framework": "f1"},
            "from": "raw",
            "patterns": [{"regex": r"v=(?P<v>\d+)"}],
        },
        "set": {"v": "{{v}}"},
    }]
    run_resolve_lenses(lenses, graph)
    assert graph.nodes[0]["v"] == "1"
    assert "v" not in graph.nodes[1]


def test_back_compat_legacy_field_and_pattern():
    """Old-style lenses with `field:` and `pattern:` still work."""
    graph = Graph()
    graph.nodes.append(_make_node("E", url="https://host.example/api"))
    lenses = [{
        "name": "legacy",
        "scope": "resolve",
        "match": {
            "label": "E",
            "field": "url",
            "pattern": r"https?://(?P<host>[^/]+)(?P<path>/.*)?",
        },
        "set": {"host": "{{host}}", "path": "{{path}}"},
    }]
    n = run_resolve_lenses(lenses, graph)
    assert n == 1
    assert graph.nodes[0]["host"] == "host.example"
    assert graph.nodes[0]["path"] == "/api"


def test_patterns_list_tries_each_in_order():
    graph = Graph()
    graph.nodes.append(_make_node("X", raw='cacheNames={"a","b"}'))
    lenses = [{
        "name": "multi-pat",
        "scope": "resolve",
        "match": {
            "label": "X",
            "from": "raw",
            "patterns": [
                {"regex": r'cacheNames\s*=\s*"(?P<c>[^"]+)"'},   # won't match
                {"regex": r'cacheNames\s*=\s*\{\s*(?P<c>[^}]+)'},  # will match
            ],
        },
        "set": {"cache": "{{c}}"},
    }]
    run_resolve_lenses(lenses, graph)
    assert '"a","b"' in graph.nodes[0]["cache"]
