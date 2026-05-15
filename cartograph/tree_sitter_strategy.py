from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import Edge, Node

try:
    import tree_sitter as ts
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

_LANGUAGES: dict[str, Any] = {}


def tree_sitter_available() -> bool:
    return HAS_TREE_SITTER


def _get_language(name: str) -> Any:
    if name in _LANGUAGES:
        return _LANGUAGES[name]
    if name == "java":
        import tree_sitter_java as mod
    elif name in ("javascript", "js"):
        import tree_sitter_javascript as mod
    else:
        raise ValueError(f"no tree-sitter grammar for language: {name}")
    lang = ts.Language(mod.language())
    _LANGUAGES[name] = lang
    return lang


def _infer_language(rel_path: str) -> str:
    ext = Path(rel_path).suffix
    return {
        ".java": "java",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "javascript",
        ".tsx": "javascript",
    }.get(ext, "")


def run_tree_sitter_strategy(
    lens: dict[str, Any],
    rel_path: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    if not HAS_TREE_SITTER:
        raise RuntimeError(
            "tree-sitter strategy requires tree-sitter and language grammar packages. "
            "Install with: pip install tree-sitter tree-sitter-java tree-sitter-javascript"
        )

    match = lens["match"]
    ts_config = match.get("tree_sitter", {})
    lang_name = ts_config.get("language") or _infer_language(rel_path)
    if not lang_name:
        return [], []

    language = _get_language(lang_name)
    parser = ts.Parser(language)
    tree = parser.parse(content.encode("utf-8"))

    extractor = ts_config.get("extractor", "annotation-method")
    if extractor == "annotation-method":
        return _ts_annotation_method(lens, tree.root_node, rel_path, content, service)
    if extractor == "walk":
        return _ts_walk_extract(lens, tree.root_node, rel_path, content, service)
    raise ValueError(f"unknown tree-sitter extractor: {extractor}")


def _ts_annotation_method(
    lens: dict[str, Any],
    root: Any,
    rel: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    from .engine import _emit_node, _join_paths

    match = lens["match"]
    emit = lens["emit"]
    ts_config = match.get("tree_sitter", {})
    class_annotations = set(ts_config.get("class_annotations", match.get("class_annotations", [])))
    base_path_annotation = ts_config.get("base_path_annotation", match.get("base_path_annotation", "@RequestMapping"))
    method_annotations = ts_config.get("method_annotations", match.get("method_annotations", {}))

    nodes: list[Node] = []
    edges: list[Edge] = []

    for cls_node in _find_nodes(root, "class_declaration"):
        class_anns = _get_annotations(cls_node)
        if not class_annotations.intersection(set(class_anns.keys())):
            continue

        class_name = _field_text(cls_node, "name") or Path(rel).stem
        base_path = _annotation_string_arg(class_anns.get(base_path_annotation)) or ""

        body = cls_node.child_by_field_name("body")
        if not body:
            continue

        for method_node in _find_nodes(body, "method_declaration"):
            method_anns = _get_annotations(method_node)
            method_name = _field_text(method_node, "name") or "handler"

            matched = False
            for ann_prefix, http_method in method_annotations.items():
                ann_key = f"@{ann_prefix}Mapping"
                if ann_key in method_anns:
                    method_path = _annotation_string_arg(method_anns[ann_key]) or ""
                    captures = {
                        "base_path": base_path,
                        "method_path": method_path,
                        "path": _join_paths(base_path, method_path),
                        "http_method": http_method,
                        "class_name": class_name,
                        "method_name": method_name,
                    }
                    line_no = method_node.start_point[0] + 1
                    nodes.append(_emit_node(emit, captures, rel, line_no, service))
                    matched = True

            if not matched and "@RequestMapping" in method_anns:
                rm_node = method_anns["@RequestMapping"]
                http_method = _annotation_request_method(rm_node) or "GET"
                method_path = _annotation_string_arg(rm_node) or ""
                captures = {
                    "base_path": base_path,
                    "method_path": method_path,
                    "path": _join_paths(base_path, method_path),
                    "http_method": http_method,
                    "class_name": class_name,
                    "method_name": method_name,
                }
                line_no = method_node.start_point[0] + 1
                nodes.append(_emit_node(emit, captures, rel, line_no, service))

    return nodes, edges


def _ts_walk_extract(
    lens: dict[str, Any],
    root: Any,
    rel: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    from .engine import _emit_node

    match = lens["match"]
    emit = lens["emit"]
    ts_config = match.get("tree_sitter", {})
    node_type = ts_config.get("node_type", "")
    capture_fields = ts_config.get("capture_fields", [])

    nodes: list[Node] = []
    edges: list[Edge] = []

    for found in _find_nodes(root, node_type):
        captures: dict[str, Any] = {}
        for field_name in capture_fields:
            child = found.child_by_field_name(field_name)
            if child:
                captures[field_name] = child.text.decode("utf-8")
        line_no = found.start_point[0] + 1
        nodes.append(_emit_node(emit, captures, rel, line_no, service))

    return nodes, edges


def _find_nodes(root: Any, node_type: str) -> list[Any]:
    results = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == node_type:
            results.append(node)
        stack.extend(reversed(node.children))
    return results


def _get_annotations(node: Any) -> dict[str, Any]:
    annotations: dict[str, Any] = {}
    for child in node.children:
        if child.type == "modifiers":
            for mod_child in child.children:
                if mod_child.type == "annotation":
                    name = _annotation_name(mod_child)
                    if name:
                        annotations[name] = mod_child
                elif mod_child.type == "marker_annotation":
                    name = _annotation_name(mod_child)
                    if name:
                        annotations[name] = mod_child
    return annotations


def _annotation_name(ann_node: Any) -> str | None:
    for child in ann_node.children:
        if child.type == "identifier":
            return f"@{child.text.decode('utf-8')}"
    return None


def _annotation_string_arg(ann_node: Any) -> str | None:
    if ann_node is None:
        return None
    for child in ann_node.children:
        if child.type == "annotation_argument_list":
            for arg_child in child.children:
                if arg_child.type == "string_literal":
                    text = arg_child.text.decode("utf-8")
                    return text.strip('"').strip("'")
                if arg_child.type == "element_value_pair":
                    for pair_child in arg_child.children:
                        if pair_child.type == "string_literal":
                            text = pair_child.text.decode("utf-8")
                            return text.strip('"').strip("'")
    return None


def _annotation_request_method(ann_node: Any) -> str | None:
    if ann_node is None:
        return None
    text = ann_node.text.decode("utf-8") if ann_node.text else ""
    m = re.search(r"RequestMethod\.(\w+)", text)
    return m.group(1).upper() if m else None


def _field_text(node: Any, field_name: str) -> str | None:
    child = node.child_by_field_name(field_name)
    if child:
        return child.text.decode("utf-8")
    return None
