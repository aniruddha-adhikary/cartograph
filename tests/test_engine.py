from __future__ import annotations

from cartograph.engine import run_source_lens


def test_regex_strategy_extracts_nodes() -> None:
    lens = {
        "name": "django-url",
        "scope": "source",
        "match": {
            "files": ["*.py"],
            "strategy": "regex",
            "patterns": [
                {"regex": r"path\(['\"](?P<route>[^'\"]+)['\"].*?(?P<handler>\w+)\)", "per_line": True},
            ],
        },
        "emit": {
            "label": "Endpoint",
            "schema": {"path": "string", "handler": "string", "http_method": "string"},
            "values": {"path": "{{route}}", "handler": "{{handler}}", "http_method": "GET"},
            "source": "lens:django-url",
            "confidence": "high",
        },
    }
    content = """from django.urls import path
from . import views
urlpatterns = [
    path('orders/', views.order_list),
    path('orders/<int:pk>/', views.order_detail),
]
"""
    nodes, edges = run_source_lens(lens, "urls.py", content, service="myapp")
    assert len(nodes) == 2
    assert nodes[0].label == "Endpoint"
    assert nodes[0].get("path") == "orders/"
    assert nodes[0].get("handler") == "order_list"
    assert nodes[1].get("path") == "orders/<int:pk>/"


def test_annotation_method_strategy_extracts_spring_endpoints() -> None:
    lens = {
        "name": "spring-rest",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "annotation-method",
            "class_annotations": ["@RestController", "@Controller"],
            "base_path_annotation": "@RequestMapping",
            "method_annotations": {"Get": "GET", "Post": "POST"},
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
    content = """@RestController
@RequestMapping("/orders")
class OrderController {
    @GetMapping("/{id}")
    public String getOrder() { return "ok"; }

    @PostMapping
    public String createOrder() { return "ok"; }
}"""
    nodes, edges = run_source_lens(lens, "OrderController.java", content, service="order-service")
    assert len(nodes) == 2
    assert nodes[0].get("http_method") == "GET"
    assert nodes[0].get("path") == "/orders/{id}"
    assert nodes[0].get("handler") == "OrderController.getOrder"
    assert nodes[1].get("http_method") == "POST"


def test_annotation_method_skips_file_without_class_annotation() -> None:
    lens = {
        "name": "spring-rest",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "annotation-method",
            "class_annotations": ["@RestController"],
            "method_annotations": {"Get": "GET"},
        },
        "emit": {
            "label": "Endpoint",
            "schema": {"path": "string"},
            "values": {"path": "{{method_path}}"},
            "source": "lens:x",
            "confidence": "high",
        },
    }
    content = """class PlainService {
    @GetMapping("/foo")
    public String foo() { return "ok"; }
}"""
    nodes, edges = run_source_lens(lens, "PlainService.java", content, service="svc")
    assert len(nodes) == 0


def test_token_line_strategy_extracts_matching_lines() -> None:
    lens = {
        "name": "http-calls",
        "scope": "source",
        "match": {
            "files": ["*.java"],
            "strategy": "token-line",
            "tokens": ["RestTemplate", "getForObject"],
            "extract": r'"(?P<url>https?://[^"]+|/[A-Za-z0-9_./{}-]+)"',
        },
        "emit": {
            "label": "HttpCall",
            "schema": {"url": "string"},
            "values": {"url": "{{url}}"},
            "source": "lens:http-call",
            "confidence": "high",
        },
    }
    content = """String result = restTemplate.getForObject("http://orders-service/api/orders", String.class);
String other = somethingElse();
String result2 = restTemplate.getForObject("http://billing-service/api/invoices", String.class);"""
    nodes, edges = run_source_lens(lens, "Client.java", content, service="web")
    assert len(nodes) == 2
    assert nodes[0].get("url") == "http://orders-service/api/orders"
    assert nodes[1].get("url") == "http://billing-service/api/invoices"


def test_xml_element_strategy_extracts_struts_actions() -> None:
    lens = {
        "name": "struts-action",
        "scope": "source",
        "match": {
            "files": ["*.xml"],
            "strategy": "xml-element",
            "tag": "action",
            "attrs": ["name", "class", "method"],
        },
        "emit": {
            "label": "Action",
            "schema": {"name": "string", "class_name": "string", "method": "string"},
            "values": {"name": "{{name}}", "class_name": "{{class}}", "method": "{{method}}"},
            "source": "lens:struts-action",
            "confidence": "high",
        },
    }
    content = """<struts>
  <package name="default" namespace="/admin">
    <action name="listUsers" class="com.example.UserAction" method="list">
      <result>/WEB-INF/views/users.jsp</result>
    </action>
  </package>
</struts>"""
    nodes, edges = run_source_lens(lens, "struts.xml", content, service="legacy")
    assert len(nodes) == 1
    assert nodes[0].get("name") == "listUsers"
    assert nodes[0].get("class_name") == "com.example.UserAction"
    assert nodes[0].get("method") == "list"


def test_config_key_strategy_extracts_application_name() -> None:
    lens = {
        "name": "spring-app-name",
        "scope": "source",
        "match": {
            "files": ["*.properties", "*.yaml", "*.yml"],
            "strategy": "config-key",
            "key_pattern": r"spring\.application\.name\s*=\s*(?P<app_name>.+)",
        },
        "emit": {
            "label": "ConfigProperty",
            "schema": {"key": "string", "value": "string"},
            "values": {"key": "spring.application.name", "value": "{{app_name}}"},
            "source": "lens:spring-config",
            "confidence": "high",
        },
    }
    content = """server.port=8080
spring.application.name=permits-api
spring.kafka.bootstrap-servers=localhost:9092"""
    nodes, edges = run_source_lens(lens, "application.properties", content, service="permits-api")
    assert len(nodes) == 1
    assert nodes[0].get("value") == "permits-api"
