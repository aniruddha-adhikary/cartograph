# Tier 1: Unified Lens Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace packs, views, and lenses with a single unified "lens" concept backed by a generic execution engine, and add CLI authoring commands for Claude-driven lens creation.

**Architecture:** A lens is a JSON definition with `scope: source` (matches files, emits nodes/edges) or `scope: graph` (matches graph patterns, returns subgraphs). A generic engine loads lens definitions, dispatches to the appropriate matcher (regex for source, hand-rolled Cypher for graph), and produces typed Node/Edge objects. The indexer becomes a thin orchestrator that runs source lenses, then linkers, then dedup.

**Tech Stack:** Python 3.11+ stdlib only. No new dependencies in this tier.

---

### Task 1: Create Node and Edge base types with props bag

**Files:**
- Create: `cartograph/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from cartograph.models import Node, Edge

def test_node_to_dict_flattens_props():
    n = Node(id="svc:f:1:abc", label="Endpoint", service="svc", file="f.java",
             line=1, source="lens:spring-rest", confidence="high",
             props={"path": "/orders", "http_method": "GET", "handler": "OrderCtrl.get"})
    d = n.to_dict()
    assert d["id"] == "svc:f:1:abc"
    assert d["path"] == "/orders"
    assert d["http_method"] == "GET"
    assert "props" not in d

def test_node_from_dict_splits_universal_fields():
    d = {"id": "svc:f:1:abc", "label": "Endpoint", "service": "svc", "file": "f.java",
         "line": 1, "source": "lens:x", "confidence": "high", "path": "/orders"}
    n = Node.from_dict(d)
    assert n.label == "Endpoint"
    assert n.props == {"path": "/orders"}

def test_edge_to_dict_uses_from_and_to_keys():
    e = Edge(type="CROSSES_TIER", from_id="a", to_id="b", source="lens:x", confidence="high",
             props={"from_service": "svc1", "to_service": "svc2"})
    d = e.to_dict()
    assert d["from"] == "a"
    assert d["to"] == "b"
    assert d["from_service"] == "svc1"
    assert "from_id" not in d
    assert "to_id" not in d

def test_edge_from_dict_maps_from_to_to_from_id_to_id():
    d = {"type": "HANDLES", "from": "a", "to": "b", "source": "x", "confidence": "high"}
    e = Edge.from_dict(d)
    assert e.from_id == "a"
    assert e.to_id == "b"

def test_node_get_reads_from_props():
    n = Node(id="x", label="Endpoint", service="s", file="f", line=1,
             source="src", confidence="high", props={"path": "/foo"})
    assert n.get("path") == "/foo"
    assert n.get("missing", "default") == "default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cartograph.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# cartograph/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

UNIVERSAL_NODE_FIELDS = {"id", "label", "service", "file", "line", "source", "confidence"}
UNIVERSAL_EDGE_FIELDS = {"type", "from", "to", "from_id", "to_id", "source", "confidence"}


@dataclass
class Node:
    id: str
    label: str
    service: str
    file: str
    line: int
    source: str
    confidence: Literal["high", "medium", "low"]
    props: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "service": self.service,
            "file": self.file, "line": self.line, "source": self.source,
            "confidence": self.confidence, **self.props,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        props = {k: v for k, v in data.items() if k not in UNIVERSAL_NODE_FIELDS}
        return cls(
            id=data["id"], label=data["label"], service=data.get("service", ""),
            file=data.get("file", ""), line=data.get("line", 0),
            source=data.get("source", ""), confidence=data.get("confidence", "high"),
            props=props,
        )


@dataclass
class Edge:
    type: str
    from_id: str
    to_id: str
    source: str
    confidence: Literal["high", "medium", "low"]
    props: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type, "from": self.from_id, "to": self.to_id,
            "source": self.source, "confidence": self.confidence, **self.props,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        props = {k: v for k, v in data.items() if k not in UNIVERSAL_EDGE_FIELDS}
        return cls(
            type=data["type"], from_id=data.get("from", data.get("from_id", "")),
            to_id=data.get("to", data.get("to_id", "")),
            source=data.get("source", ""), confidence=data.get("confidence", "high"),
            props=props,
        )


@dataclass
class SchemaRegistry:
    node_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    edge_types: dict[str, dict[str, str]] = field(default_factory=dict)

    def register_node(self, label: str, schema: dict[str, str]) -> None:
        existing = self.node_labels.get(label, {})
        self.node_labels[label] = {**existing, **schema}

    def register_edge(self, edge_type: str, schema: dict[str, str]) -> None:
        existing = self.edge_types.get(edge_type, {})
        self.edge_types[edge_type] = {**existing, **schema}

    def to_dict(self) -> dict[str, Any]:
        return {"node_labels": self.node_labels, "edge_types": self.edge_types}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchemaRegistry:
        return cls(
            node_labels=data.get("node_labels", {}),
            edge_types=data.get("edge_types", {}),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cartograph/models.py tests/test_models.py
git commit -m "feat: add Node/Edge base types with schema-driven props bag"
```

---

### Task 2: Define unified lens JSON schema and validator

**Files:**
- Create: `cartograph/lens_schema.py`
- Test: `tests/test_lens_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lens_schema.py
import pytest
from cartograph.lens_schema import validate_lens, LensValidationError

def test_valid_source_lens_passes():
    lens = {
        "name": "spring-rest-endpoint",
        "scope": "source",
        "match": {"files": ["*.java"], "strategy": "annotation-method",
                  "class_annotations": ["@RestController", "@Controller"]},
        "emit": {"label": "Endpoint",
                 "schema": {"path": "string", "http_method": "string"},
                 "values": {"path": "{{base_path}}/{{method_path}}", "http_method": "{{http_method}}"},
                 "source": "lens:spring-rest-endpoint", "confidence": "high"},
    }
    validate_lens(lens)  # should not raise

def test_valid_graph_lens_passes():
    lens = {
        "name": "kafka-bus-view",
        "scope": "graph",
        "match": {"query": "MATCH (p:KafkaProducer)-[d:KAFKA_DELIVERS]->(c:KafkaConsumer) RETURN p, d, c"},
        "emit": {"returns": {"p": "KafkaProducer", "d": "KAFKA_DELIVERS", "c": "KafkaConsumer"}},
    }
    validate_lens(lens)

def test_missing_name_raises():
    with pytest.raises(LensValidationError, match="name"):
        validate_lens({"scope": "source", "match": {}, "emit": {}})

def test_invalid_scope_raises():
    with pytest.raises(LensValidationError, match="scope"):
        validate_lens({"name": "x", "scope": "invalid", "match": {}, "emit": {}})

def test_source_lens_requires_files_in_match():
    with pytest.raises(LensValidationError, match="files"):
        validate_lens({"name": "x", "scope": "source", "match": {"strategy": "regex"}, "emit": {"label": "X", "schema": {}, "values": {}, "source": "x", "confidence": "high"}})

def test_source_lens_requires_emit_label():
    with pytest.raises(LensValidationError, match="label"):
        validate_lens({"name": "x", "scope": "source", "match": {"files": ["*.java"]}, "emit": {"schema": {}, "values": {}, "source": "x", "confidence": "high"}})

def test_graph_lens_requires_query_in_match():
    with pytest.raises(LensValidationError, match="query"):
        validate_lens({"name": "x", "scope": "graph", "match": {}, "emit": {}})

def test_load_lens_file_loads_list_of_lenses(tmp_path):
    import json
    from cartograph.lens_schema import load_lens_file
    path = tmp_path / "test.json"
    path.write_text(json.dumps([
        {"name": "a", "scope": "graph", "match": {"query": "MATCH (n) RETURN n"}, "emit": {"returns": {}}},
        {"name": "b", "scope": "graph", "match": {"query": "MATCH (n) RETURN n"}, "emit": {"returns": {}}},
    ]))
    lenses = load_lens_file(path)
    assert [l["name"] for l in lenses] == ["a", "b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lens_schema.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# cartograph/lens_schema.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LensValidationError(ValueError):
    pass


def validate_lens(lens: dict[str, Any]) -> None:
    if not isinstance(lens, dict):
        raise LensValidationError("lens must be a dict")
    if not lens.get("name"):
        raise LensValidationError("lens must have a non-empty 'name'")
    scope = lens.get("scope")
    if scope not in ("source", "graph"):
        raise LensValidationError(f"lens scope must be 'source' or 'graph', got '{scope}'")
    if not isinstance(lens.get("match"), dict):
        raise LensValidationError("lens must have a 'match' dict")
    if not isinstance(lens.get("emit"), dict):
        raise LensValidationError("lens must have an 'emit' dict")
    if scope == "source":
        _validate_source_lens(lens)
    else:
        _validate_graph_lens(lens)


def _validate_source_lens(lens: dict[str, Any]) -> None:
    match = lens["match"]
    if "files" not in match or not isinstance(match["files"], list):
        raise LensValidationError("source lens match must include 'files' list")
    emit = lens["emit"]
    if not emit.get("label"):
        raise LensValidationError("source lens emit must include 'label'")
    if not isinstance(emit.get("schema", {}), dict):
        raise LensValidationError("source lens emit.schema must be a dict")
    if not isinstance(emit.get("values", {}), dict):
        raise LensValidationError("source lens emit.values must be a dict")


def _validate_graph_lens(lens: dict[str, Any]) -> None:
    match = lens["match"]
    if not match.get("query"):
        raise LensValidationError("graph lens match must include 'query'")


def load_lens_file(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    for lens in data:
        validate_lens(lens)
    return data


def load_lens_dir(directory: Path) -> list[dict[str, Any]]:
    lenses: list[dict[str, Any]] = []
    if not directory.exists():
        return lenses
    for path in sorted(directory.glob("*.json")):
        lenses.extend(load_lens_file(path))
    return lenses
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_lens_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cartograph/lens_schema.py tests/test_lens_schema.py
git commit -m "feat: add unified lens schema definition and validator"
```

---

### Task 3: Build the source lens regex engine

The engine executes `scope: source` lenses. For Tier 1, it supports these match strategies:

- `annotation-method` — class annotations + method annotations (Spring REST pattern)
- `token-line` — find lines containing tokens, extract with regex (Kafka, HTTP clients)
- `xml-element` — match XML tags by name/attribute (Struts, web.xml, SQL mappers)
- `config-key` — match config file keys (gateway routes, application names)
- `regex` — raw regex with named captures (general purpose, Claude's escape hatch)

**Files:**
- Create: `cartograph/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write failing tests for the regex strategy (simplest)**

```python
# tests/test_engine.py
from cartograph.engine import run_source_lens

def test_regex_strategy_extracts_nodes():
    lens = {
        "name": "django-url",
        "scope": "source",
        "match": {
            "files": ["*.py"],
            "strategy": "regex",
            "patterns": [{"regex": r"path\(['\"](?P<route>[^'\"]+)['\"].*?(?P<handler>\w+)\)", "per_line": True}],
        },
        "emit": {
            "label": "Endpoint",
            "schema": {"path": "string", "handler": "string", "http_method": "string"},
            "values": {"path": "{{route}}", "handler": "{{handler}}", "http_method": "GET"},
            "source": "lens:django-url",
            "confidence": "high",
        },
    }
    content = '''from django.urls import path
from . import views
urlpatterns = [
    path('orders/', views.order_list),
    path('orders/<int:pk>/', views.order_detail),
]
'''
    nodes, edges = run_source_lens(lens, "urls.py", content, service="myapp")
    assert len(nodes) == 2
    assert nodes[0].label == "Endpoint"
    assert nodes[0].get("path") == "orders/"
    assert nodes[0].get("handler") == "order_list"
    assert nodes[1].get("path") == "orders/<int:pk>/"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py::test_regex_strategy_extracts_nodes -v`
Expected: FAIL

- [ ] **Step 3: Write engine implementation with regex strategy**

```python
# cartograph/engine.py
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .models import Node, Edge


def run_source_lens(
    lens: dict[str, Any],
    rel_path: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    strategy = lens["match"].get("strategy", "regex")
    if strategy == "regex":
        return _regex_strategy(lens, rel_path, content, service)
    if strategy == "annotation-method":
        return _annotation_method_strategy(lens, rel_path, content, service)
    if strategy == "token-line":
        return _token_line_strategy(lens, rel_path, content, service)
    if strategy == "xml-element":
        return _xml_element_strategy(lens, rel_path, content, service)
    if strategy == "config-key":
        return _config_key_strategy(lens, rel_path, content, service)
    raise ValueError(f"unknown source lens strategy: {strategy}")


def _regex_strategy(
    lens: dict[str, Any], rel: str, content: str, service: str,
) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    emit = lens["emit"]
    for pattern_spec in lens["match"].get("patterns", []):
        regex = pattern_spec["regex"]
        if pattern_spec.get("per_line", False):
            for line_no, line in enumerate(content.splitlines(), 1):
                m = re.search(regex, line)
                if m:
                    captures = m.groupdict()
                    node = _emit_node(emit, captures, rel, line_no, service)
                    nodes.append(node)
        else:
            for m in re.finditer(regex, content):
                captures = m.groupdict()
                line_no = content.count("\n", 0, m.start()) + 1
                node = _emit_node(emit, captures, rel, line_no, service)
                nodes.append(node)
    return nodes, edges


def _annotation_method_strategy(
    lens: dict[str, Any], rel: str, content: str, service: str,
) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    match = lens["match"]
    emit = lens["emit"]
    lines = content.splitlines()
    class_annotations = match.get("class_annotations", [])
    base_path_annotation = match.get("base_path_annotation", "@RequestMapping")
    method_annotations = match.get("method_annotations", {})

    has_class_annotation = any(
        any(ann in line for ann in class_annotations) for line in lines
    )
    if not has_class_annotation:
        return nodes, edges

    base_path = ""
    class_name = Path(rel).stem
    for idx, line in enumerate(lines, 1):
        if base_path_annotation in line and not any(
            f"{k}Mapping" in line for k in method_annotations
        ):
            base_path = _first_string(line) or base_path
        class_match = re.search(r"\bclass\s+(\w+)", line)
        if class_match:
            class_name = class_match.group(1)

    for idx, line in enumerate(lines, 1):
        for ann_prefix, http_method in method_annotations.items():
            pattern = rf"@{re.escape(ann_prefix)}Mapping\s*(?:\((.*)\))?"
            m = re.search(pattern, line)
            if m:
                method_path = _first_string(m.group(1) or line) or ""
                method_name = _next_java_method(lines, idx) or "handler"
                full_path = _join_paths(base_path, method_path)
                captures = {
                    "base_path": base_path,
                    "method_path": method_path,
                    "http_method": http_method,
                    "class_name": class_name,
                    "method_name": method_name,
                }
                node = _emit_node(emit, captures, rel, idx, service)
                nodes.append(node)
    return nodes, edges


def _token_line_strategy(
    lens: dict[str, Any], rel: str, content: str, service: str,
) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    match = lens["match"]
    emit = lens["emit"]
    tokens = match.get("tokens", [])
    extract_regex = match.get("extract")

    for idx, line in enumerate(content.splitlines(), 1):
        if not any(token in line for token in tokens):
            continue
        captures = {"line": line, "line_no": str(idx)}
        if extract_regex:
            m = re.search(extract_regex, line)
            if m:
                captures.update(m.groupdict())
        node = _emit_node(emit, captures, rel, idx, service)
        nodes.append(node)
    return nodes, edges


def _xml_element_strategy(
    lens: dict[str, Any], rel: str, content: str, service: str,
) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    match = lens["match"]
    emit = lens["emit"]
    tag = match.get("tag", "")
    attrs_capture = match.get("attrs", [])

    for m in re.finditer(rf"<{re.escape(tag)}\b([^>]*)(?:/>|>(.*?)</{re.escape(tag)}>)", content, flags=re.DOTALL | re.IGNORECASE):
        attr_str = m.group(1)
        body = m.group(2) or ""
        attrs = _xml_attrs(attr_str)
        captures = {a: attrs.get(a, "") for a in attrs_capture}
        captures["body"] = body.strip()
        line_no = content.count("\n", 0, m.start()) + 1
        node = _emit_node(emit, captures, rel, line_no, service)
        nodes.append(node)
    return nodes, edges


def _config_key_strategy(
    lens: dict[str, Any], rel: str, content: str, service: str,
) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    match = lens["match"]
    emit = lens["emit"]
    key_pattern = match.get("key_pattern", "")

    for idx, line in enumerate(content.splitlines(), 1):
        m = re.search(key_pattern, line)
        if m:
            captures = m.groupdict()
            node = _emit_node(emit, captures, rel, idx, service)
            nodes.append(node)
    return nodes, edges


def _emit_node(
    emit: dict[str, Any], captures: dict[str, Any], rel: str, line_no: int, service: str,
) -> Node:
    values = emit.get("values", {})
    props: dict[str, Any] = {}
    for key, template in values.items():
        props[key] = _resolve_template(template, captures)
    digest = hashlib.sha1(
        f"{service}:{rel}:{line_no}:{emit.get('label', '')}:{emit.get('source', '')}:{props}".encode()
    ).hexdigest()[:10]
    return Node(
        id=f"{service}:{rel}:{line_no}:{digest}",
        label=emit.get("label", ""),
        service=service,
        file=rel,
        line=line_no,
        source=emit.get("source", ""),
        confidence=emit.get("confidence", "high"),
        props=props,
    )


def _resolve_template(template: str, captures: dict[str, Any]) -> Any:
    if not isinstance(template, str):
        return template
    result = template
    for key, value in captures.items():
        result = result.replace(f"{{{{{key}}}}}", str(value) if value is not None else "")
    return result


def _first_string(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r'"([^"]+)"|\'([^\']+)\'', text)
    return next((g for g in m.groups() if g), None) if m else None


def _next_java_method(lines: list[str], start: int) -> str | None:
    for line in lines[start: min(start + 8, len(lines))]:
        m = re.search(r"\b(?:public|private|protected)?\s*(?:[\w<>?,\s]+)\s+(\w+)\s*\(", line)
        if m and m.group(1) not in {"if", "for", "while", "switch"}:
            return m.group(1)
    return None


def _join_paths(base: str, child: str) -> str:
    if not base and not child:
        return "/"
    return "/" + "/".join(part.strip("/") for part in (base, child) if part and part != "/")


def _xml_attrs(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2) or m.group(3)
        for m in re.finditer(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", text)
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Write additional tests for annotation-method strategy**

```python
# append to tests/test_engine.py
def test_annotation_method_strategy_extracts_spring_endpoints():
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
            "values": {"path": "{{base_path}}/{{method_path}}", "http_method": "{{http_method}}",
                       "handler": "{{class_name}}.{{method_name}}"},
            "source": "lens:spring-rest",
            "confidence": "high",
        },
    }
    content = '''
@RestController
@RequestMapping("/orders")
class OrderController {
    @GetMapping("/{id}")
    public String getOrder() { return "ok"; }

    @PostMapping
    public String createOrder() { return "ok"; }
}
'''.strip()
    nodes, edges = run_source_lens(lens, "OrderController.java", content, service="order-service")
    assert len(nodes) == 2
    assert nodes[0].get("http_method") == "GET"
    assert nodes[0].get("path") == "/orders/{id}"
    assert nodes[0].get("handler") == "OrderController.getOrder"
    assert nodes[1].get("http_method") == "POST"
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add cartograph/engine.py tests/test_engine.py
git commit -m "feat: add source lens engine with regex and annotation-method strategies"
```

---

### Task 4: Convert existing pack configs to source lens definitions

Translate `spring.json` and `javascript.json` pack configs into lens definition JSON files.

**Files:**
- Create: `cartograph/builtins/spring_rest.json`
- Create: `cartograph/builtins/spring_kafka.json`
- Create: `cartograph/builtins/spring_http_client.json`
- Create: `cartograph/builtins/spring_gateway.json`
- Create: `cartograph/builtins/express_routes.json`
- Create: `cartograph/builtins/kafkajs.json`
- Create: `cartograph/builtins/struts.json`
- Create: `cartograph/builtins/j2ee_web.json`
- Create: `cartograph/builtins/sql.json`
- Create: `cartograph/builtins/react.json`

Each file is a JSON array of lens definitions that encode the extraction patterns currently hardcoded in `indexer.py`. These are created iteratively — one framework at a time, verified against existing golden output.

- [ ] **Step 1: Create spring_rest.json**

This encodes the Spring REST controller extraction from `index_java` lines 517-572.

- [ ] **Step 2: Test spring_rest.json against CityPermits fixture**

Run the engine on the permits-api Java files and verify endpoints match the golden graph.

- [ ] **Step 3: Create remaining builtin lens files one at a time**

Each lens file is tested by running the engine against the appropriate fixture and comparing output to the golden graph.

- [ ] **Step 4: Commit**

```bash
git add cartograph/builtins/
git commit -m "feat: convert pack extraction patterns to source lens definitions"
```

---

### Task 5: Wire engine into indexer alongside existing code

**Files:**
- Modify: `cartograph/indexer.py`

The indexer gains an `engine_mode` flag. When enabled, it uses the lens engine instead of hardcoded extraction. Both paths coexist during migration.

- [ ] **Step 1: Add engine import and dual-path flag**

- [ ] **Step 2: Run golden tests with engine_mode=False (existing path)**

Verify nothing is broken.

- [ ] **Step 3: Run golden tests with engine_mode=True (new path)**

Compare output. Fix lens definitions until output matches.

- [ ] **Step 4: Once golden output matches, remove the old extraction path**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: wire lens engine into indexer, remove hardcoded extraction"
```

---

### Task 6: Convert views and existing lenses to scope:graph lens definitions

**Files:**
- Create: `cartograph/builtins/graph_views.json`
- Modify: `cartograph/engine.py` — add `run_graph_lens` function

- [ ] **Step 1: Convert `views/default.json` to graph lens definitions**

- [ ] **Step 2: Convert existing Kuzu lens spec format to graph lens format**

- [ ] **Step 3: Add `run_graph_lens` that delegates to existing `lens_specs.py` Cypher interpreter**

The hand-rolled Cypher interpreter stays for now (replaced in Tier 5). The graph lens format just wraps it.

- [ ] **Step 4: Test against golden query outputs**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: convert views and lenses to scope:graph lens definitions"
```

---

### Task 7: Add CLI authoring commands

**Files:**
- Modify: `cartograph/cli.py`

- [ ] **Step 1: Add `test-lens` subcommand**

Tests a lens definition against source files without persisting.

- [ ] **Step 2: Add `persist-lens` subcommand**

Writes a validated lens to `.cartograph/lenses/`.

- [ ] **Step 3: Add `list-lenses` as alias for `lens list`**

- [ ] **Step 4: Update `discover-packs` to `discover` and include lens schema in output**

- [ ] **Step 5: Write tests for CLI commands**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: add lens authoring CLI commands (test-lens, persist-lens, discover)"
```

---

### Task 8: Delete old code and verify

**Files:**
- Delete: `cartograph/serve.py`
- Delete: `cartograph/tools.py`
- Delete: `cartograph/views.py`
- Delete: `cartograph/packs/spring.json`
- Delete: `cartograph/packs/javascript.json`
- Delete: `cartograph/views/default.json`
- Modify: `cartograph/cli.py` — remove `serve` and `tools` commands, remove view imports
- Modify: tests — remove `test_server_dispatch_supports_mcp_style_tool_calls` and `test_tools_command_exposes_cli_first_catalog`

- [ ] **Step 1: Delete files**

- [ ] **Step 2: Update imports throughout codebase**

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All remaining tests pass. Two MCP/tools tests are removed.

- [ ] **Step 4: Run golden snapshot tests**

Run: `python -m pytest tests/test_m2_golden.py -v`
Expected: PASS — graph output unchanged.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: remove serve.py, tools.py, views.py, pack configs — unified lens model complete"
```

---

### Task 9: Add schema registry to graph output

**Files:**
- Modify: `cartograph/indexer.py`
- Modify: `cartograph/models.py`

- [ ] **Step 1: During indexing, collect emit schemas from all active lenses**

- [ ] **Step 2: Write schema registry into `graph.meta.schema`**

- [ ] **Step 3: Test that indexed graph contains schema registry**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: persist schema registry in graph meta from lens emit schemas"
```
