"""Tests for the JS/TS branch of the method-call extractor.

Validates that receiver-type binding works across the inference sources:
  - `new T(...)` in lexical/variable declarations (JS + TS)
  - TS `type_annotation` on lexical_declaration
  - TS `type_annotation` on required_parameter
  - TS class field type annotation (`private x: T`)
  - JS constructor `this.x = new T()` assignment

Each test also asserts the fail-closed behavior: untyped JS variables with no
`new T(...)` initializer do NOT match, even if the property name is right.
"""
from __future__ import annotations

import pytest

from cartograph.tree_sitter_strategy import tree_sitter_available

pytestmark = pytest.mark.skipif(
    not tree_sitter_available(), reason="tree-sitter not installed"
)

from cartograph.engine import run_source_lens


def _lens(method_name: str, receiver_type: str, language: str = "javascript", capture_as: str = "value"):
    return {
        "name": "test-js-mc",
        "scope": "source",
        "match": {
            "files": ["*.js", "*.ts"],
            "strategy": "tree-sitter",
            "tree_sitter": {
                "language": language,
                "extractor": "method-call",
                "method_name": method_name,
                "receiver_type": receiver_type,
                "capture_as": capture_as,
            },
        },
        "emit": {
            "label": "Call",
            "schema": {"target": "string"},
            "values": {"target": "{{value}}"},
            "source": "lens:test-js-mc",
            "confidence": "high",
        },
    }


# ----- JS: `new T(...)` initializer drives the binding -----


def test_js_new_expression_initializer_resolves_variable() -> None:
    lens = _lens("add", "SolrClient")
    src = """
    import SolrClient from "solr-client";
    const rooboo = new SolrClient({host: "x"});
    async function f() { await rooboo.add("doc-a"); }
    """
    nodes, _ = run_source_lens(lens, "f.js", src, service="svc")
    assert len(nodes) == 1
    assert nodes[0].line == 4


def test_js_unrelated_receiver_is_skipped() -> None:
    lens = _lens("add", "SolrClient")
    src = """
    import SolrClient from "solr-client";
    const other = new SomethingElse();
    other.add("nope");
    """
    nodes, _ = run_source_lens(lens, "f.js", src, service="svc")
    assert nodes == []


def test_js_untyped_variable_fails_closed() -> None:
    """JS variable with no `new T(...)` initializer and no type annotation:
    we cannot statically know its type, so the lens must NOT fire."""
    lens = _lens("add", "SolrClient")
    src = """
    const opaque = makeClient();   // dynamic factory, no static type
    opaque.add("dynamic-call");
    """
    nodes, _ = run_source_lens(lens, "f.js", src, service="svc")
    assert nodes == []


def test_js_multiple_locals_with_same_type_all_match() -> None:
    lens = _lens("publish", "MqttClient")
    src = """
    const a = new MqttClient();
    const b = new MqttClient();
    function run() {
      a.publish("topic/a");
      b.publish("topic/b");
    }
    """
    nodes, _ = run_source_lens(lens, "f.js", src, service="svc")
    assert len(nodes) == 2


# ----- TS: explicit type annotations -----


def test_ts_lexical_type_annotation_resolves() -> None:
    lens = _lens("add", "SolrClient", language="typescript")
    src = """
    import {SolrClient} from "solr-client";
    const rooboo: SolrClient = makeClient();
    async function f() { await rooboo.add("doc-b"); }
    """
    nodes, _ = run_source_lens(lens, "f.ts", src, service="svc")
    assert len(nodes) == 1


def test_ts_required_parameter_type_annotation_resolves() -> None:
    lens = _lens("add", "SolrClient", language="typescript")
    src = """
    function handle(client: SolrClient) {
      client.add("from-param");
    }
    """
    nodes, _ = run_source_lens(lens, "f.ts", src, service="svc")
    assert len(nodes) == 1


def test_ts_class_field_type_annotation_resolves_this_receiver() -> None:
    lens = _lens("add", "SolrClient", language="typescript")
    src = """
    class Service {
      private rooboo: SolrClient;
      constructor(c: SolrClient) { this.rooboo = c; }
      async run() { await this.rooboo.add("doc-c"); }
    }
    """
    nodes, _ = run_source_lens(lens, "f.ts", src, service="svc")
    assert len(nodes) == 1


# ----- JS: this.x = new T() inside constructor -----


def test_js_constructor_assignment_binds_this_field() -> None:
    lens = _lens("add", "SolrClient")
    src = """
    class Service {
      constructor() {
        this.client = new SolrClient();
      }
      run() {
        this.client.add("doc-d");
      }
    }
    """
    nodes, _ = run_source_lens(lens, "f.js", src, service="svc")
    assert len(nodes) == 1


# ----- Chained / opaque receivers fail closed -----


def test_chained_receiver_fails_closed() -> None:
    """Chained call: a().add(...) - receiver is a call_expression, no static
    type, must not match."""
    lens = _lens("add", "SolrClient")
    src = """
    import SolrClient from "solr-client";
    function provide() { return new SolrClient(); }
    function run() { provide().add("chained"); }
    """
    nodes, _ = run_source_lens(lens, "f.js", src, service="svc")
    assert nodes == []


# ----- Multiple accepted types via receiver_types list -----


def test_receiver_types_list_accepts_multiple() -> None:
    lens = _lens("publish", "MqttClient")
    lens["match"]["tree_sitter"]["receiver_types"] = ["MqttClient", "MqttClientV5"]
    del lens["match"]["tree_sitter"]["receiver_type"]
    src = """
    const a = new MqttClient();
    const b = new MqttClientV5();
    const c = new OtherClient();
    function run() {
      a.publish("t/a");
      b.publish("t/b");
      c.publish("t/c");  // should not match
    }
    """
    nodes, _ = run_source_lens(lens, "f.js", src, service="svc")
    assert len(nodes) == 2


# ----- Import-gate (token-line strategy) -----


def test_import_gate_skips_files_without_matching_import() -> None:
    """import_gate filter on token-line strategy should suppress matches
    when the configured import substring is absent from the file."""
    lens = {
        "name": "test-import-gate",
        "scope": "source",
        "match": {
            "files": ["*.js"],
            "strategy": "token-line",
            "tokens": [".publish("],
            "import_gate": ["mqtt"],
        },
        "emit": {
            "label": "Publish",
            "schema": {"line": "string"},
            "values": {"line": "{{line}}"},
            "source": "lens:test-import-gate",
            "confidence": "high",
        },
    }
    src_no_import = """
    import {Client} from "ioredis";
    const r = new Client();
    r.publish("channel", "msg");
    """
    nodes, _ = run_source_lens(lens, "no-mqtt.js", src_no_import, service="svc")
    assert nodes == [], "import_gate must suppress matches without the import"

    src_with_import = """
    import mqtt from "mqtt";
    const c = mqtt.connect("mqtt://x");
    c.publish("topic", "msg");
    """
    nodes, _ = run_source_lens(lens, "with-mqtt.js", src_with_import, service="svc")
    assert len(nodes) == 1
