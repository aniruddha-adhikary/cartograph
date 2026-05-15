from __future__ import annotations

import json
from pathlib import Path

import pytest

from cartograph.cli import main
from cartograph.indexer import index_workspace
from cartograph.install import install
from cartograph.verify import verify_graph


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def test_lens_overlay_adds_custom_controller_annotation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = workspace / "orders"
    (service / "src/main/java/example").mkdir(parents=True)
    (service / "cartograph.yaml").write_text("name: orders\n", encoding="utf-8")
    (service / "src/main/java/example/OrderController.java").write_text(
        """
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@CartographRest
@RequestMapping("/orders")
class OrderController {
    @GetMapping("/{id}")
    String getOrder() {
        return "ok";
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    lenses = tmp_path / "lenses"
    write_json(
        lenses / "custom-rest.json",
        {
            "name": "custom-rest-endpoint",
            "scope": "source",
            "match": {
                "files": ["*.java"],
                "strategy": "annotation-method",
                "class_annotations": ["@CartographRest"],
                "base_path_annotation": "@RequestMapping",
                "method_annotations": {"Get": "GET", "Post": "POST"},
            },
            "emit": {
                "label": "Endpoint",
                "schema": {"http_method": "string", "path": "string", "handler": "string"},
                "values": {"http_method": "{{http_method}}", "path": "{{path}}", "handler": "{{class_name}}.{{method_name}}"},
                "source": "lens:custom-rest",
                "confidence": "high",
            },
        },
    )

    graph = index_workspace(workspace, lens_dirs=[lenses]).to_dict()

    endpoints = [node for node in graph["nodes"] if node["label"] == "Endpoint"]
    assert [(endpoint["http_method"], endpoint["path"]) for endpoint in endpoints] == [("GET", "/orders/{id}")]


def test_pack_overlay_lists_extend_instead_of_replacing_defaults(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = workspace / "orders"
    (service / "src/main/java/example").mkdir(parents=True)
    (service / "cartograph.yaml").write_text("name: orders\n", encoding="utf-8")
    (service / "src/main/java/example/Controllers.java").write_text(
        """
package example;

@RestController
class DefaultController {
    @GetMapping("/default")
    String defaultRoute() { return "ok"; }
}

@CartographRest
class CustomController {
    @GetMapping("/custom")
    String customRoute() { return "ok"; }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    packs = tmp_path / "packs"
    write_json(packs / "spring.json", {"rest": {"controller_annotations": ["@CartographRest"]}})

    graph = index_workspace(workspace, packs_dir=packs).to_dict()

    endpoint_paths = {node["path"] for node in graph["nodes"] if node["label"] == "Endpoint"}
    assert endpoint_paths == {"/default", "/custom"}


def test_lens_overlay_defines_custom_message_bus(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    producer = workspace / "orders"
    consumer = workspace / "billing"
    for service in (producer, consumer):
        (service / "src/main/java/example").mkdir(parents=True)
        (service / "cartograph.yaml").write_text(f"name: {service.name}\n", encoding="utf-8")
    (producer / "src/main/java/example/Orders.java").write_text(
        """
package example;

class Orders {
    void created(EventBus bus) {
        bus.publish("orders.created", "payload");
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (consumer / "src/main/java/example/Billing.java").write_text(
        """
package example;

class Billing {
    @TopicListener(topics = "orders.created")
    void onCreated(String event) {}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    lenses = tmp_path / "lenses"
    write_json(
        lenses / "eventbus.json",
        [
            {
                "name": "eventbus-producer",
                "scope": "source",
                "match": {
                    "files": ["*.java"],
                    "strategy": "token-line",
                    "tokens": [".publish("],
                    "extract": "\"(?P<topic>[^\"]+)\""
                },
                "emit": {
                    "label": "MessageProducer",
                    "schema": {"message_role": "string", "bus": "string", "topic": "string"},
                    "values": {"message_role": "producer", "bus": "eventbus", "topic": "{{topic}}"},
                    "source": "lens:eventbus",
                    "confidence": "high",
                },
            },
            {
                "name": "eventbus-consumer",
                "scope": "source",
                "match": {
                    "files": ["*.java"],
                    "strategy": "regex",
                    "patterns": [
                        {"regex": "@TopicListener\\s*\\(\\s*topics\\s*=\\s*\"(?P<topic>[^\"]+)\"", "per_line": True}
                    ],
                },
                "emit": {
                    "label": "MessageConsumer",
                    "schema": {"message_role": "string", "bus": "string", "topics": "list"},
                    "values": {"message_role": "consumer", "bus": "eventbus", "topics": ["{{topic}}"]},
                    "source": "lens:eventbus",
                    "confidence": "high",
                },
            },
        ],
    )

    graph = index_workspace(workspace, lens_dirs=[lenses]).to_dict()

    assert any(node["label"] == "MessageProducer" and node["bus"] == "eventbus" for node in graph["nodes"])
    assert any(node["label"] == "MessageConsumer" and node["bus"] == "eventbus" for node in graph["nodes"])
    assert any(
        edge["type"] == "MESSAGE_DELIVERS" and edge["from_service"] == "orders" and edge["to_service"] == "billing"
        for edge in graph["edges"]
    )


def test_query_uses_view_layer_override(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    graph = write_json(
        tmp_path / "graph.json",
        {
            "nodes": [
                {"id": "svc", "label": "Service", "service": "orders", "name": "Orders"},
                {"id": "ep", "label": "Endpoint", "service": "orders", "path": "/orders"},
            ],
            "edges": [],
        },
    )
    layer = tmp_path / "layer"
    write_json(
        layer / "views" / "endpoints.json",
        {
            "endpoints": {
                "kind": "nodes",
                "label": "Service",
                "sort": ["service"],
            }
        },
    )

    assert main(["query", "--graph", str(graph), "--name", "endpoints", "--layer-dir", str(layer)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result == [{"id": "svc", "label": "Service", "name": "Orders", "service": "orders"}]


def test_cli_runs_local_plugin_with_args(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    graph = write_json(
        tmp_path / "graph.json",
        {
            "nodes": [{"id": "svc", "label": "Service"}, {"id": "ep", "label": "Endpoint"}],
            "edges": [{"type": "HANDLES", "from": "svc", "to": "ep"}],
        },
    )
    plugin = tmp_path / "service_count.py"
    plugin.write_text(
        """
def run(graph, args):
    return {
        "label": args["label"],
        "matches": len([node for node in graph["nodes"] if node["label"] == args["label"]]),
        "edges": len(graph["edges"]),
    }
""".lstrip(),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-plugin",
                "--graph",
                str(graph),
                "--plugin",
                str(plugin),
                "--args",
                '{"label": "Service"}',
                "--allow-plugin",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"edges": 1, "label": "Service", "matches": 1}


def test_install_writes_cli_first_agent_instructions(tmp_path: Path) -> None:
    written = install("codex", tmp_path)

    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    skill = (tmp_path / ".agents/skills/cartograph/SKILL.md").read_text(encoding="utf-8")
    hooks = (tmp_path / ".codex/hooks.json").read_text(encoding="utf-8")

    assert tmp_path / "AGENTS.md" in written
    assert "cartograph tools" in agents
    assert "cartograph flow" in agents
    assert "cartograph serve" in agents
    assert "cartograph tools" in skill
    assert "Cartograph CLI queries" in hooks


def test_explicit_layers_override_project_layer_in_order(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project_views = workspace / ".cartograph" / "views"
    layer = tmp_path / "team-layer"
    graph = write_json(
        tmp_path / "graph.json",
        {
            "nodes": [
                {"id": "svc", "label": "Service", "service": "orders"},
                {"id": "ep", "label": "Endpoint", "service": "orders", "path": "/orders"},
            ],
            "edges": [],
        },
    )
    write_json(project_views / "summary.json", {"summary": {"kind": "nodes", "label": "Service"}})
    write_json(layer / "views" / "summary.json", {"summary": {"kind": "nodes", "label": "Endpoint"}})

    assert (
        main(
            [
                "query",
                "--graph",
                str(graph),
                "--name",
                "summary",
                "--workspace",
                str(workspace),
                "--layer-dir",
                str(layer),
            ]
        )
        == 0
    )

    result = json.loads(capsys.readouterr().out)
    assert result == [{"id": "ep", "label": "Endpoint", "path": "/orders", "service": "orders"}]


def test_verifier_reports_duplicate_node_ids_and_missing_required_edges(tmp_path: Path) -> None:
    graph = write_json(
        tmp_path / "graph.json",
        {
            "nodes": [
                {"id": "same", "label": "KafkaProducer", "service": "orders", "topic": "orders.created"},
                {"id": "same", "label": "KafkaConsumer", "service": "billing", "topics": ["orders.created"]},
            ],
            "edges": [],
        },
    )
    suite = write_json(
        tmp_path / "suite.json",
        {
            "no_duplicate_node_ids": True,
            "required_edges": [
                {
                    "type": "KAFKA_DELIVERS",
                    "from_service": "orders",
                    "to_service": "billing",
                    "topic": "orders.created",
                }
            ],
        },
    )

    errors = verify_graph(graph, suite)

    assert "duplicate node id same" in errors
    assert any(error.startswith("missing required edge") for error in errors)


def test_index_workspace_excludes_test_paths_from_fixture_workspace() -> None:
    workspace = Path(__file__).parent / "fixtures" / "test-path-workspace"

    graph = index_workspace(workspace).to_dict()
    endpoint_paths = {node["path"] for node in graph["nodes"] if node["label"] == "Endpoint"}
    indexed_files = {node["file"] for node in graph["nodes"]}

    assert any("ProdController" in f for f in indexed_files)
    assert not any("TestController" in f for f in indexed_files)
    assert endpoint_paths == {"/prod"}

    graph_with_tests = index_workspace(workspace, include_test_paths=True).to_dict()
    all_endpoint_paths = {node["path"] for node in graph_with_tests["nodes"] if node["label"] == "Endpoint"}
    assert {"/prod", "/test-only"} <= all_endpoint_paths


def test_cartograph_yaml_can_add_exclusion_patterns_and_enable_tests(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = workspace / "orders"
    (service / "src/main/java/example").mkdir(parents=True)
    (service / "src/generated/java/example").mkdir(parents=True)
    (service / "src/test/java/example").mkdir(parents=True)
    (service / "cartograph.yaml").write_text(
        """
name: orders
exclude:
  - src/generated/**
""".lstrip(),
        encoding="utf-8",
    )
    (service / "src/main/java/example/ProdController.java").write_text(
        """
@RestController
class Prod {
  @GetMapping("/prod")
  String prod(){ return ""; }
}
""".lstrip(),
        encoding="utf-8",
    )
    (service / "src/generated/java/example/GeneratedController.java").write_text(
        """
@RestController
class Generated {
  @GetMapping("/generated")
  String generated(){ return ""; }
}
""".lstrip(),
        encoding="utf-8",
    )
    (service / "src/test/java/example/TestController.java").write_text(
        """
@RestController
class TestOnly {
  @GetMapping("/test")
  String test(){ return ""; }
}
""".lstrip(),
        encoding="utf-8",
    )

    graph = index_workspace(workspace).to_dict()
    assert {node["path"] for node in graph["nodes"] if node["label"] == "Endpoint"} == {"/prod"}

    (service / "cartograph.yaml").write_text("name: orders\ninclude_test_paths: true\n", encoding="utf-8")
    graph_with_tests = index_workspace(workspace).to_dict()
    assert {"/prod", "/generated", "/test"} <= {
        node["path"] for node in graph_with_tests["nodes"] if node["label"] == "Endpoint"
    }


def test_legacy_java_fixture_indexes_struts_j2ee_and_database_patterns() -> None:
    workspace = Path(__file__).parents[1] / "fixtures" / "legacy-java-workspace"

    graph = index_workspace(workspace).to_dict()

    endpoints = {node["path"] for node in graph["nodes"] if node["label"] == "Endpoint"}
    labels = {node["label"] for node in graph["nodes"]}
    operations = {node.get("operation") for node in graph["nodes"] if node["label"] == "DatabaseQuery"}

    assert "/legacy/submitOrder.action" in endpoints
    assert "/legacy/servlet" in endpoints
    assert {"Action", "Servlet", "DatabaseQuery"} <= labels
    assert {"SELECT", "UPDATE", "CALL"} <= operations


def test_cartograph_yaml_parser_handles_nested_and_inline_lists(tmp_path: Path) -> None:
    service = tmp_path / "service"
    service.mkdir()
    (service / "cartograph.yaml").write_text(
        """
name: quoted-service
include_test_paths: true
exclude: [generated/**, tmp/**]
metadata:
  owner: platform
""".lstrip(),
        encoding="utf-8",
    )

    graph = index_workspace(tmp_path).to_dict()

    assert graph["meta"]["services"] == ["quoted-service"]
    from cartograph.discovery import service_config

    config = service_config(service)
    assert config["name"] == "quoted-service"
    assert config["include_test_paths"] is True
    assert config["exclude"] == ["generated/**", "tmp/**"]
    assert config["metadata"]["owner"] == "platform"
