from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .models import Edge, Node


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
                    nodes.append(_emit_node(emit, captures, rel, line_no, service))
        else:
            for m in re.finditer(regex, content):
                captures = m.groupdict()
                line_no = content.count("\n", 0, m.start()) + 1
                nodes.append(_emit_node(emit, captures, rel, line_no, service))
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
    for line in lines:
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
                captures = {
                    "base_path": base_path,
                    "method_path": method_path,
                    "path": _join_paths(base_path, method_path),
                    "http_method": http_method,
                    "class_name": class_name,
                    "method_name": method_name,
                }
                nodes.append(_emit_node(emit, captures, rel, idx, service))
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
        captures: dict[str, Any] = {"line": line, "line_no": str(idx)}
        if extract_regex:
            m = re.search(extract_regex, line)
            if m:
                captures.update(m.groupdict())
            else:
                continue
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

    if "|" in tag:
        tag_pattern = "(?:" + "|".join(re.escape(t) for t in tag.split("|")) + ")"
    else:
        tag_pattern = re.escape(tag)

    for m in re.finditer(
        rf"<({tag_pattern})\b([^>]*)(?:/>|>(.*?)</\1>)",
        content, flags=re.DOTALL | re.IGNORECASE,
    ):
        matched_tag = m.group(1)
        attr_str = m.group(2)
        body = m.group(3) or ""
        attrs = _xml_attrs(attr_str)
        captures = {a: attrs.get(a, "") for a in attrs_capture}
        captures["body"] = body.strip()
        captures["_tag"] = matched_tag.upper()
        line_no = content.count("\n", 0, m.start()) + 1
        nodes.append(_emit_node(emit, captures, rel, line_no, service))
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
            nodes.append(_emit_node(emit, captures, rel, idx, service))
    return nodes, edges


def _emit_node(
    emit: dict[str, Any], captures: dict[str, Any], rel: str, line_no: int, service: str,
) -> Node:
    captures.setdefault("_file_stem", Path(rel).stem)
    captures.setdefault("_line", str(line_no))
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
    for line in lines[start:min(start + 8, len(lines))]:
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
