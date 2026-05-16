from __future__ import annotations

import pytest

from cartograph.tree_sitter_strategy import tree_sitter_available

pytestmark = pytest.mark.skipif(not tree_sitter_available(), reason="tree-sitter not installed")

from cartograph.engine import run_source_lens


def _lens(extractor: str, target: str):
    return {
        "name": "test-supertype",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "tree-sitter",
            "tree_sitter": {
                "language": "java",
                "extractor": extractor,
                "superclass": target,
                "typearg_index": 0,
                "capture_as": "entity_type",
            },
        },
        "emit": {
            "label": "Repository",
            "schema": {"entity_type": "string", "class_name": "string"},
            "values": {"entity_type": "{{entity_type}}", "class_name": "{{class_name}}"},
            "source": "lens:test-supertype",
            "confidence": "high",
        },
    }


# ----- A7: new extractor name matches implements -----

def test_supertype_matches_implements() -> None:
    """Quarkus Panache: `class FooRepo implements PanacheRepository<Foo>`."""
    lens = _lens("class-supertype-typearg", "PanacheRepository")
    content = """public class FruitRepository implements PanacheRepository<Fruit> {
    }"""
    nodes, _ = run_source_lens(lens, "FruitRepository.java", content, service="svc")
    assert len(nodes) == 1
    assert nodes[0].get("entity_type") == "Fruit"
    assert nodes[0].get("class_name") == "FruitRepository"


def test_supertype_matches_extends() -> None:
    lens = _lens("class-supertype-typearg", "AbstractAggregateDomainEventPublisher")
    content = """public class OrderPublisher extends AbstractAggregateDomainEventPublisher<Order, OrderEvent> {
    }"""
    nodes, _ = run_source_lens(lens, "OrderPublisher.java", content, service="svc")
    assert len(nodes) == 1
    assert nodes[0].get("entity_type") == "Order"


def test_supertype_matches_among_multiple_interfaces() -> None:
    lens = _lens("class-supertype-typearg", "PanacheRepository")
    content = """public class FruitRepository
        implements Serializable, PanacheRepository<Fruit>, AutoCloseable {
    }"""
    nodes, _ = run_source_lens(lens, "FruitRepository.java", content, service="svc")
    assert len(nodes) == 1
    assert nodes[0].get("entity_type") == "Fruit"


def test_supertype_skips_non_generic_implements() -> None:
    """`implements PanacheRepository` without a type argument is skipped."""
    lens = _lens("class-supertype-typearg", "PanacheRepository")
    content = """public class FruitRepository implements PanacheRepository {
    }"""
    nodes, _ = run_source_lens(lens, "FruitRepository.java", content, service="svc")
    assert nodes == []


def test_supertype_skips_unrelated() -> None:
    lens = _lens("class-supertype-typearg", "PanacheRepository")
    content = """public class Plain extends Object {
    }"""
    nodes, _ = run_source_lens(lens, "Plain.java", content, service="svc")
    assert nodes == []


# ----- Back-compat alias: class-extends-typearg -----

def test_legacy_extends_extractor_still_works() -> None:
    """Eventuate-tram lens uses the legacy extractor name with extends; must keep working."""
    lens = _lens("class-extends-typearg", "AbstractAggregateDomainEventPublisher")
    content = """public class OrderPublisher extends AbstractAggregateDomainEventPublisher<Order, OrderEvent> {
    }"""
    nodes, _ = run_source_lens(lens, "OrderPublisher.java", content, service="svc")
    assert len(nodes) == 1
    assert nodes[0].get("entity_type") == "Order"
    assert nodes[0].get("class_name") == "OrderPublisher"


def test_legacy_extractor_now_also_matches_implements() -> None:
    """The legacy name is an alias for the generalized extractor — implements works too."""
    lens = _lens("class-extends-typearg", "PanacheRepository")
    content = """public class FruitRepository implements PanacheRepository<Fruit> {
    }"""
    nodes, _ = run_source_lens(lens, "FruitRepository.java", content, service="svc")
    assert len(nodes) == 1
    assert nodes[0].get("entity_type") == "Fruit"
