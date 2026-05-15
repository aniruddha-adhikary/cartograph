from __future__ import annotations

from pathlib import Path

from cartograph.lens_runner import (
    build_schema_registry,
    lenses_for_file,
    load_all_lenses,
    run_lenses_on_file,
)


def test_load_all_lenses_includes_builtins() -> None:
    lenses = load_all_lenses()
    names = {l["name"] for l in lenses}
    assert "spring-rest-endpoint" in names
    assert "express-routes" in names


def test_load_all_lenses_overlay_replaces_builtin(tmp_path: Path) -> None:
    import json
    overlay_dir = tmp_path / "lenses"
    overlay_dir.mkdir()
    custom = {
        "name": "spring-rest-endpoint",
        "scope": "source",
        "match": {"files": ["*.java"], "strategy": "regex", "patterns": []},
        "emit": {"label": "CustomEndpoint", "schema": {}, "values": {}, "source": "x", "confidence": "high"},
    }
    (overlay_dir / "custom.json").write_text(json.dumps(custom))
    lenses = load_all_lenses(overlay_dirs=[overlay_dir])
    spring = [l for l in lenses if l["name"] == "spring-rest-endpoint"]
    assert len(spring) == 1
    assert spring[0]["emit"]["label"] == "CustomEndpoint"


def test_lenses_for_file_filters_by_pattern() -> None:
    lenses = load_all_lenses()
    java_lenses = lenses_for_file(lenses, "src/main/OrderController.java")
    names = {l["name"] for l in java_lenses}
    assert "spring-rest-endpoint" in names
    assert "express-routes" not in names

    js_lenses = lenses_for_file(lenses, "src/routes.js")
    js_names = {l["name"] for l in js_lenses}
    assert "express-routes" in js_names
    assert "spring-rest-endpoint" not in js_names


def test_run_lenses_on_java_file() -> None:
    lenses = load_all_lenses()
    content = """@RestController
@RequestMapping("/api/orders")
class OrderController {
    @GetMapping("/{id}")
    public Order getOrder() { return null; }
}"""
    nodes, edges = run_lenses_on_file(lenses, "OrderController.java", content, service="orders")
    endpoints = [n for n in nodes if n.label == "Endpoint"]
    assert len(endpoints) >= 1
    assert endpoints[0].get("path") == "/api/orders/{id}"


def test_run_lenses_on_properties_file() -> None:
    lenses = load_all_lenses()
    content = "spring.application.name=my-service\nserver.port=8080\n"
    nodes, edges = run_lenses_on_file(lenses, "application.properties", content, service="my-svc")
    configs = [n for n in nodes if n.label == "ConfigProperty"]
    assert len(configs) == 1
    assert configs[0].get("value") == "my-service"


def test_build_schema_registry_from_lenses() -> None:
    lenses = load_all_lenses()
    registry = build_schema_registry(lenses)
    assert "path" in registry.node_labels.get("Endpoint", {})
    assert "http_method" in registry.node_labels.get("Endpoint", {})
    assert "url" in registry.node_labels.get("HttpCall", {})
