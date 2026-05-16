from __future__ import annotations

import pytest

from cartograph.tree_sitter_strategy import tree_sitter_available

pytestmark = pytest.mark.skipif(not tree_sitter_available(), reason="tree-sitter not installed")

from cartograph.engine import run_source_lens


def _to_lens(**ts_overrides):
    """Build a baseline `method-call` lens matching `.to("topic")` calls."""
    ts_config = {
        "language": "java",
        "extractor": "method-call",
        "method_name": "to",
        "arg_index": 0,
        "capture_as": "topic",
    }
    ts_config.update(ts_overrides)
    return {
        "name": "test-to",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "tree-sitter",
            "tree_sitter": ts_config,
        },
        "emit": {
            "label": "Producer",
            "schema": {"topic": "string", "raw": "string"},
            "values": {"topic": "{{topic}}", "raw": "{{topic_text}}"},
            "source": "lens:test-to",
            "confidence": "high",
        },
    }


# ----- A1: back-compat (no filters) -----

def test_method_call_back_compat_matches_all() -> None:
    lens = _to_lens()
    content = """public class Mixed {
        public void run(KStream<String,String> stream, RabbitTemplate rabbit) {
            stream.to("kafka-topic");
            rabbit.to("rabbit-dest");
        }
    }"""
    nodes, _ = run_source_lens(lens, "Mixed.java", content, service="svc")
    topics = sorted(n.get("topic") for n in nodes)
    assert topics == ["kafka-topic", "rabbit-dest"]


# ----- A1: parent_class_extends -----

def test_parent_class_extends_keeps_inside_matching_class() -> None:
    lens = _to_lens(parent_class_extends=["RouteBuilder"])
    content = """public class MyRoute extends RouteBuilder {
        public void configure() {
            from("direct:in").to("kafka:out");
        }
    }"""
    nodes, _ = run_source_lens(lens, "MyRoute.java", content, service="svc")
    assert [n.get("topic") for n in nodes] == ["kafka:out"]


def test_parent_class_extends_skips_outside_class() -> None:
    lens = _to_lens(parent_class_extends=["RouteBuilder"])
    content = """public class NotARoute {
        public void configure() {
            something.to("not-camel");
        }
    }"""
    nodes, _ = run_source_lens(lens, "NotARoute.java", content, service="svc")
    assert nodes == []


def test_parent_class_extends_strips_generics() -> None:
    lens = _to_lens(parent_class_extends=["RouteBuilder"])
    content = """public class MyRoute extends RouteBuilder<String> {
        public void configure() {
            from("x").to("kafka:y");
        }
    }"""
    nodes, _ = run_source_lens(lens, "MyRoute.java", content, service="svc")
    assert [n.get("topic") for n in nodes] == ["kafka:y"]


def test_parent_class_extends_matches_super_interfaces() -> None:
    lens = _to_lens(parent_class_extends=["EndpointRouteBuilder"])
    content = """public class MyRoute implements EndpointRouteBuilder {
        public void configure() {
            from("x").to("kafka:z");
        }
    }"""
    nodes, _ = run_source_lens(lens, "MyRoute.java", content, service="svc")
    assert [n.get("topic") for n in nodes] == ["kafka:z"]


# ----- A1: receiver_type -----

def test_receiver_type_matches_field() -> None:
    lens = _to_lens(receiver_type="KStream")
    content = """public class Topology {
        private KStream<String,String> stream;
        public void wire() {
            stream.to("matching-topic");
        }
    }"""
    nodes, _ = run_source_lens(lens, "Topology.java", content, service="svc")
    assert [n.get("topic") for n in nodes] == ["matching-topic"]


def test_receiver_type_matches_local_variable() -> None:
    lens = _to_lens(receiver_type="KStream")
    content = """public class Topology {
        public void wire() {
            KStream<String,String> s = builder.stream("in");
            s.to("matching-topic");
        }
    }"""
    nodes, _ = run_source_lens(lens, "Topology.java", content, service="svc")
    assert [n.get("topic") for n in nodes] == ["matching-topic"]


def test_receiver_type_matches_this_field() -> None:
    lens = _to_lens(receiver_type="KStream")
    content = """public class Topology {
        private KStream<String,String> stream;
        public void wire() {
            this.stream.to("via-this");
        }
    }"""
    nodes, _ = run_source_lens(lens, "Topology.java", content, service="svc")
    assert [n.get("topic") for n in nodes] == ["via-this"]


def test_receiver_type_skips_wrong_type() -> None:
    lens = _to_lens(receiver_type="KStream")
    content = """public class Wrong {
        private RabbitTemplate rabbit;
        public void wire() {
            rabbit.to("not-kafka");
        }
    }"""
    nodes, _ = run_source_lens(lens, "Wrong.java", content, service="svc")
    assert nodes == []


def test_receiver_type_skips_chain_fail_closed() -> None:
    """Chained calls like KStream.filter(...).to("topic") cannot be resolved
    statically (the receiver of `.to` is itself a method_invocation). The
    extractor must fail closed when receiver_type is set."""
    lens = _to_lens(receiver_type="KStream")
    content = """public class Chain {
        public void wire(KStream<String,String> s) {
            s.filter(x -> true).to("from-chain");
        }
    }"""
    nodes, _ = run_source_lens(lens, "Chain.java", content, service="svc")
    assert nodes == []


def test_receiver_type_unqualified_uses_enclosing_class() -> None:
    """An unqualified call `to(...)` inside class `Foo` has receiver type `Foo`."""
    lens = _to_lens(receiver_type="MyBuilder")
    content = """public class MyBuilder {
        public void configure() {
            to("self-call");
        }
    }"""
    nodes, _ = run_source_lens(lens, "MyBuilder.java", content, service="svc")
    assert [n.get("topic") for n in nodes] == ["self-call"]


# ----- A1: combined AND -----

def test_both_filters_must_hold() -> None:
    lens = _to_lens(receiver_type="KStream", parent_class_extends=["RouteBuilder"])
    content = """public class A extends RouteBuilder {
        private KStream<String,String> stream;
        public void configure() {
            stream.to("both-hold");
        }
    }
    public class B extends RouteBuilder {
        public void configure() {
            rabbit.to("class-ok-receiver-wrong");
        }
    }
    public class C {
        private KStream<String,String> stream;
        public void configure() {
            stream.to("receiver-ok-class-wrong");
        }
    }"""
    nodes, _ = run_source_lens(lens, "Multi.java", content, service="svc")
    topics = [n.get("topic") for n in nodes]
    assert topics == ["both-hold"]
