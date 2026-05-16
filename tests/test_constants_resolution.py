"""Tests for the same-file Java constants pre-pass."""
from __future__ import annotations

from cartograph.graph import Graph
from cartograph.linkers import apply_constants_to_nodes


def _node(label: str, file: str, **props) -> dict:
    base = {
        "id": f"svc:{file}:1:abcd",
        "label": label,
        "service": "svc",
        "file": file,
        "line": 1,
        "source": "lens:test",
        "confidence": "high",
    }
    base.update(props)
    return base


def test_const_resolves_when_target_prop_unset():
    g = Graph()
    g.nodes.append(_node("MessageProducer", "Foo.java", destination_const="Resources.QUEUE_NAME"))
    consts = {"Foo.java": {"Resources.QUEUE_NAME": "demoQueue", "QUEUE_NAME": "demoQueue"}}
    resolved = apply_constants_to_nodes(g, consts)
    assert resolved == 1
    assert g.nodes[0]["destination"] == "demoQueue"


def test_const_lookup_falls_back_to_unqualified_leaf():
    g = Graph()
    g.nodes.append(_node("MessageProducer", "Bar.java", topic_const="OtherClass.TOPIC"))
    consts = {"Bar.java": {"TOPIC": "events-v1"}}
    apply_constants_to_nodes(g, consts)
    assert g.nodes[0]["topic"] == "events-v1"


def test_const_skipped_when_target_already_set():
    g = Graph()
    g.nodes.append(_node("X", "F.java", destination_const="X.K", destination="already"))
    consts = {"F.java": {"X.K": "different"}}
    apply_constants_to_nodes(g, consts)
    assert g.nodes[0]["destination"] == "already"


def test_const_unknown_symbol_leaves_node_untouched():
    g = Graph()
    g.nodes.append(_node("X", "F.java", destination_const="Unknown.SYMBOL"))
    consts = {"F.java": {"OTHER": "v"}}
    resolved = apply_constants_to_nodes(g, consts)
    assert resolved == 0
    assert "destination" not in g.nodes[0]


def test_const_no_constants_for_file_is_noop():
    g = Graph()
    g.nodes.append(_node("X", "F.java", destination_const="K"))
    apply_constants_to_nodes(g, {})
    assert "destination" not in g.nodes[0]


def test_const_also_patches_topics_list_when_empty():
    g = Graph()
    g.nodes.append(_node("MessageProducer", "F.java", topic_const="K", topics=[""]))
    consts = {"F.java": {"K": "real-topic"}}
    apply_constants_to_nodes(g, consts)
    assert g.nodes[0]["topic"] == "real-topic"
    assert g.nodes[0]["topics"] == ["real-topic"]


def test_const_generic_suffix_strip_for_unmapped_const_key():
    g = Graph()
    g.nodes.append(_node("X", "F.java", custom_const="K"))
    consts = {"F.java": {"K": "v"}}
    apply_constants_to_nodes(g, consts)
    assert g.nodes[0]["custom"] == "v"
