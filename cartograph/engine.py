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
    if strategy == "xml-query":
        return _xml_query_strategy(lens, rel_path, content, service)
    if strategy == "config-key":
        return _config_key_strategy(lens, rel_path, content, service)
    if strategy == "tree-sitter":
        from .tree_sitter_strategy import run_tree_sitter_strategy
        return run_tree_sitter_strategy(lens, rel_path, content, service)
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
        if (
            base_path_annotation in line
            and not any(f"{k}Mapping" in line for k in method_annotations)
            and "RequestMethod." not in line
            and "method =" not in line
        ):
            base_path = _first_string(line) or base_path
        class_match = re.search(r"\bclass\s+(\w+)", line)
        if class_match:
            class_name = class_match.group(1)

    for idx, line in enumerate(lines, 1):
        matched = False
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
                matched = True
        if not matched:
            rm = re.search(
                r"@RequestMapping\s*\(([^)]*method\s*=\s*RequestMethod\.(\w+)[^)]*)\)",
                line,
            )
            if rm:
                http_method = rm.group(2).upper()
                method_path = _first_string(rm.group(1)) or ""
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


def _xml_query_strategy(
    lens: dict[str, Any], rel: str, content: str, service: str,
) -> tuple[list[Node], list[Edge]]:
    """Run an ElementTree XPath select, emit one node per match.

    Lens match config:
      select:    str (required) — ElementTree XPath, e.g. ".//servlet-mapping"
      captures:  dict[str, str] — capture_name -> sub-selector. Each sub-selector is:
                   "@attr"          — attribute on the matched element
                   "."              — text of the matched element itself
                   "child"          — text of first <child> below the match
                   "child/grand"    — text of first <child>/<grand> below the match
                   "child/@attr"    — attribute of first <child>
                 If a capture has no match, it resolves to "".
    """
    import xml.etree.ElementTree as ET
    nodes: list[Node] = []
    edges: list[Edge] = []
    match = lens["match"]
    emit = lens["emit"]
    select = match.get("select", ".")
    captures_cfg = match.get("captures", {})

    cleaned = re.sub(r"^\s*<\?xml[^?]*\?>", "", content)
    cleaned = re.sub(r'\sxmlns(:[\w-]+)?\s*=\s*"[^"]*"', "", cleaned)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError:
        return nodes, edges

    line_starts = [0]
    for i, ch in enumerate(content):
        if ch == "\n":
            line_starts.append(i + 1)

    for el in root.findall(select):
        captures: dict[str, Any] = {"_tag": el.tag}
        for name, sub in captures_cfg.items():
            captures[name] = _xml_resolve(el, sub)
        line_no = _xml_lineno(el, content, line_starts)
        nodes.append(_emit_node(emit, captures, rel, line_no, service))
    return nodes, edges


def _xml_resolve(el: Any, selector: str) -> str:
    if selector in ("", "."):
        return (el.text or "").strip()
    if selector.startswith("@"):
        return el.get(selector[1:], "") or ""
    parts = selector.split("/")
    last = parts[-1]
    if last.startswith("@"):
        parent_path = "/".join(parts[:-1])
        target = el.find(parent_path) if parent_path else el
        return target.get(last[1:], "") if target is not None else ""
    target = el.find(selector)
    return (target.text or "").strip() if target is not None and target.text else ""


def _xml_lineno(el: Any, content: str, line_starts: list[int]) -> int:
    open_tag = f"<{el.tag}"
    idx = content.find(open_tag)
    if idx >= 0:
        for ln, start in enumerate(line_starts, 1):
            if start > idx:
                return ln - 1
    return 1


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
    captures.setdefault("_rel_path", rel)
    captures.setdefault("_rel_dir", str(Path(rel).parent).replace("\\", "/"))
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


def _resolve_template(template: Any, captures: dict[str, Any]) -> Any:
    if isinstance(template, list):
        return [_resolve_template(item, captures) for item in template]
    if not isinstance(template, str):
        return template

    def replace(match: re.Match[str]) -> str:
        # Supports {{key}}, {{key|alt_key}}, {{key|alt_key|literal_fallback}}.
        # Each pipe-separated segment is tried as a capture name first; if the last
        # segment doesn't match a known capture it's used as a literal default.
        segments = [seg.strip() for seg in match.group(1).split("|")]
        for seg in segments:
            if seg in captures and captures[seg]:
                return str(captures[seg])
        last = segments[-1]
        return last if last not in captures and len(segments) > 1 else ""

    return re.sub(r"\{\{([^{}]+)\}\}", replace, template)


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
