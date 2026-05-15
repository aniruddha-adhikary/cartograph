from __future__ import annotations

import pytest

from cartograph.tree_sitter_strategy import tree_sitter_available

pytestmark = pytest.mark.skipif(not tree_sitter_available(), reason="tree-sitter not installed")

from cartograph.engine import run_source_lens


def test_tree_sitter_annotation_method_extracts_spring_endpoints() -> None:
    lens = {
        "name": "spring-rest-ts",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "tree-sitter",
            "tree_sitter": {
                "language": "java",
                "extractor": "annotation-method",
                "class_annotations": ["@RestController", "@Controller"],
                "base_path_annotation": "@RequestMapping",
                "method_annotations": {"Get": "GET", "Post": "POST"},
            },
        },
        "emit": {
            "label": "Endpoint",
            "schema": {"path": "string", "http_method": "string", "handler": "string"},
            "values": {
                "path": "{{path}}",
                "http_method": "{{http_method}}",
                "handler": "{{class_name}}.{{method_name}}",
            },
            "source": "lens:spring-rest-ts",
            "confidence": "high",
        },
    }
    content = """@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    public Order getOrder() { return null; }

    @PostMapping
    public Order createOrder() { return null; }
}"""
    nodes, edges = run_source_lens(lens, "OrderController.java", content, service="order-svc")
    assert len(nodes) == 2
    assert nodes[0].get("http_method") == "GET"
    assert nodes[0].get("path") == "/api/orders/{id}"
    assert nodes[0].get("handler") == "OrderController.getOrder"
    assert nodes[1].get("http_method") == "POST"
    assert nodes[1].get("handler") == "OrderController.createOrder"


def test_tree_sitter_skips_non_controller_class() -> None:
    lens = {
        "name": "spring-rest-ts",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "tree-sitter",
            "tree_sitter": {
                "language": "java",
                "extractor": "annotation-method",
                "class_annotations": ["@RestController"],
                "method_annotations": {"Get": "GET"},
            },
        },
        "emit": {
            "label": "Endpoint",
            "schema": {"path": "string"},
            "values": {"path": "{{path}}"},
            "source": "lens:x",
            "confidence": "high",
        },
    }
    content = """public class PlainService {
    @GetMapping("/foo")
    public String foo() { return "ok"; }
}"""
    nodes, edges = run_source_lens(lens, "PlainService.java", content, service="svc")
    assert len(nodes) == 0


def test_tree_sitter_walk_extractor() -> None:
    lens = {
        "name": "java-methods",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "tree-sitter",
            "tree_sitter": {
                "language": "java",
                "extractor": "walk",
                "node_type": "method_declaration",
                "capture_fields": ["name"],
            },
        },
        "emit": {
            "label": "Method",
            "schema": {"name": "string"},
            "values": {"name": "{{name}}"},
            "source": "lens:java-methods",
            "confidence": "high",
        },
    }
    content = """public class Foo {
    public void bar() {}
    public int baz() { return 1; }
}"""
    nodes, edges = run_source_lens(lens, "Foo.java", content, service="svc")
    assert len(nodes) == 2
    assert nodes[0].get("name") == "bar"
    assert nodes[1].get("name") == "baz"


def test_tree_sitter_produces_same_results_as_regex() -> None:
    regex_lens = {
        "name": "spring-rest-regex",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "annotation-method",
            "class_annotations": ["@RestController", "@Controller"],
            "base_path_annotation": "@RequestMapping",
            "method_annotations": {"Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE"},
        },
        "emit": {
            "label": "Endpoint",
            "schema": {"path": "string", "http_method": "string", "handler": "string"},
            "values": {
                "path": "{{path}}",
                "http_method": "{{http_method}}",
                "handler": "{{class_name}}.{{method_name}}",
            },
            "source": "lens:spring-rest",
            "confidence": "high",
        },
    }
    ts_lens = {
        "name": "spring-rest-ts",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "tree-sitter",
            "tree_sitter": {
                "language": "java",
                "extractor": "annotation-method",
                "class_annotations": ["@RestController", "@Controller"],
                "base_path_annotation": "@RequestMapping",
                "method_annotations": {"Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE"},
            },
        },
        "emit": regex_lens["emit"],
    }
    content = """@RestController
@RequestMapping("/api/users")
public class UserController {
    @GetMapping("/{id}")
    public User getUser() { return null; }

    @PostMapping
    public User createUser() { return null; }

    @DeleteMapping("/{id}")
    public void deleteUser() {}
}"""
    regex_nodes, _ = run_source_lens(regex_lens, "UserController.java", content, service="svc")
    ts_nodes, _ = run_source_lens(ts_lens, "UserController.java", content, service="svc")

    assert len(regex_nodes) == len(ts_nodes)
    for rn, tn in zip(regex_nodes, ts_nodes):
        assert rn.get("path") == tn.get("path"), f"path mismatch: {rn.get('path')} vs {tn.get('path')}"
        assert rn.get("http_method") == tn.get("http_method")
        assert rn.get("handler") == tn.get("handler")
