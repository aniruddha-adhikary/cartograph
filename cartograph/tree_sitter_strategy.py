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
        lang = ts.Language(mod.language())
    elif name in ("javascript", "js"):
        import tree_sitter_javascript as mod
        lang = ts.Language(mod.language())
    elif name in ("typescript", "ts"):
        import tree_sitter_typescript as mod
        lang = ts.Language(mod.language_typescript())
    elif name in ("tsx", "typescript-tsx"):
        import tree_sitter_typescript as mod
        lang = ts.Language(mod.language_tsx())
    else:
        raise ValueError(f"no tree-sitter grammar for language: {name}")
    _LANGUAGES[name] = lang
    return lang


def _infer_language(rel_path: str) -> str:
    ext = Path(rel_path).suffix
    return {
        ".java": "java",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
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
    if extractor == "query":
        return _ts_query(lens, language, tree.root_node, rel_path, content, service)
    if extractor == "annotation-method":
        return _ts_annotation_method(lens, tree.root_node, rel_path, content, service)
    if extractor == "walk":
        return _ts_walk_extract(lens, tree.root_node, rel_path, content, service)
    if extractor == "method-call":
        return _ts_method_call(lens, tree.root_node, rel_path, content, service)
    if extractor == "class-extends-typearg":
        # Back-compat alias: delegate to the more general class-supertype-typearg
        # extractor. The original semantics required `extends` (superclass) only;
        # the generalized form ALSO matches `implements` (super_interfaces).
        # Because Eventuate-tram lens (the only consumer of the old name) uses
        # a `superclass` value that never appears as an interface, this widening
        # is a strict superset and back-compatible in practice.
        return _ts_class_supertype_typearg(lens, tree.root_node, rel_path, content, service)
    if extractor == "class-supertype-typearg":
        return _ts_class_supertype_typearg(lens, tree.root_node, rel_path, content, service)
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


def _ts_method_call(
    lens: dict[str, Any],
    root: Any,
    rel: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    """Find Java method invocations by name, capture the first argument.

    Lens match.tree_sitter config:
      method_name: str (required) — name of the called method (e.g. "fromChannel")
      arg_index:   int (default 0) — which argument to capture
      capture_as:  str (default "value") — base name for the capture groups

      receiver_type: str (optional) — if set, only match when the call's receiver
        (the `x` in `x.method(...)`) has a statically-inferable type whose simple
        name (generics stripped) equals this value. Fails CLOSED: if receiver type
        cannot be inferred (e.g. chained call `a.b().method(...)`, parameter, lambda
        capture), the call is SKIPPED. Receiver inference handles:
          - `identifier` receiver — searches enclosing class for a `field_declaration`
            of that name, then the enclosing method for a `local_variable_declaration`
            or formal parameter.
          - `field_access` of the form `this.x` — falls through to identifier search
            on `x` against fields.
          - missing receiver (unqualified call inside a class) — receiver type is
            the enclosing class's own simple name.
          - any other receiver shape (chained method_invocation, cast, parenthesized,
            object_creation, array_access) — skipped (fail-closed).
        LIMITATION: We do not perform full type inference. Chained fluent APIs like
        `KStream.filter(...).to("topic")` cannot be matched on receiver_type — the
        receiver of `.to` is itself a `method_invocation` and no static type is
        available. Use parent_class_extends instead for those cases.

      parent_class_extends: list[str] (optional) — only match when the call site is
        lexically inside a `class_declaration` or `interface_declaration` whose
        `superclass` (simple-name, generics stripped) OR any of its `super_interfaces`
        (simple-name, generics stripped) is in this list. Calls at file top level
        or in classes whose supertypes do not match are skipped.

      If BOTH `receiver_type` and `parent_class_extends` are set, BOTH must hold
      (AND). If NEITHER is set, behavior is unchanged from the original (matches
      every call by method name).

    Emits one node per matching call with captures:
      <capture_as>          — string-literal value (if first arg is a string)
      <capture_as>_const    — qualified identifier text (e.g. "Foo.BAR") if first arg is a field_access
      <capture_as>_class    — short class name if first arg is a class_literal (e.g. "Foo.class" -> "Foo")
      <capture_as>_text     — raw text of the argument as written in source
    """
    from .engine import _emit_node

    match = lens["match"]
    emit = lens["emit"]
    ts_config = match.get("tree_sitter", {})
    target_name = ts_config.get("method_name")
    if not target_name:
        raise ValueError("method-call extractor requires tree_sitter.method_name")
    arg_index = int(ts_config.get("arg_index", 0))
    capture_as = ts_config.get("capture_as", "value")
    receiver_type = ts_config.get("receiver_type")
    parent_class_extends = ts_config.get("parent_class_extends")
    if parent_class_extends is not None:
        parent_class_extends = set(parent_class_extends)

    nodes: list[Node] = []
    edges: list[Edge] = []

    for call_node in _find_nodes(root, "method_invocation"):
        name_node = call_node.child_by_field_name("name")
        if name_node is None or name_node.text.decode("utf-8") != target_name:
            continue

        # A1 filter: parent_class_extends — must be inside a class/interface whose
        # supertype simple-name is in the configured set.
        if parent_class_extends is not None:
            enclosing = _enclosing_class_or_interface(call_node)
            if enclosing is None:
                continue
            supertypes = _supertype_simple_names(enclosing)
            if parent_class_extends.isdisjoint(supertypes):
                continue

        # A1 filter: receiver_type — must be inferable and equal to configured value.
        if receiver_type is not None:
            inferred = _infer_receiver_type(call_node)
            if inferred is None or inferred != receiver_type:
                continue

        args_node = call_node.child_by_field_name("arguments")
        if args_node is None:
            continue
        positional = [c for c in args_node.children if c.type not in (",", "(", ")")]
        if arg_index >= len(positional):
            continue
        arg = positional[arg_index]
        captures = _capture_argument(arg, capture_as)
        if not any(captures.values()):
            continue
        line_no = call_node.start_point[0] + 1
        nodes.append(_emit_node(emit, captures, rel, line_no, service))

    return nodes, edges


def _strip_generics(name: str) -> str:
    """Return the simple-name portion of a Java type reference, stripping generics.

    `Foo<Bar>` -> `Foo`; `pkg.Foo` -> `pkg.Foo` (qualified names not split here);
    whitespace trimmed. Callers that need the unqualified leaf can split on `.`.
    """
    idx = name.find("<")
    if idx >= 0:
        name = name[:idx]
    return name.strip()


def _supertype_simple_names(class_node: Any) -> set[str]:
    """Return the set of simple-name supertypes of a class_declaration or
    interface_declaration node.

    Includes the `superclass` (for class_declaration) and every entry of
    `super_interfaces` / `extends_interfaces`. Generics are stripped.
    """
    out: set[str] = set()
    for ch in class_node.children:
        if ch.type in ("superclass", "super_interfaces", "extends_interfaces"):
            # Descend into the clause to find type_identifier / generic_type / scoped_type_identifier nodes.
            for tn in _collect_type_names(ch):
                out.add(tn)
    return out


def _collect_type_names(node: Any) -> list[str]:
    """Collect simple-name type references inside a supertype clause.

    A `superclass` clause contains either a `type_identifier`, a `generic_type`
    (which itself contains a `type_identifier`), or a `scoped_type_identifier`
    (for qualified names like `pkg.Foo`). A `super_interfaces` clause wraps a
    `type_list` containing the same.
    """
    out: list[str] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "type_identifier":
            out.append(n.text.decode("utf-8"))
            continue
        if n.type == "generic_type":
            # Take just the leading name.
            for ch in n.children:
                if ch.type == "type_identifier":
                    out.append(ch.text.decode("utf-8"))
                    break
                if ch.type == "scoped_type_identifier":
                    # qualified.Name<...> — take final segment.
                    text = ch.text.decode("utf-8")
                    out.append(text.rsplit(".", 1)[-1])
                    break
            continue
        if n.type == "scoped_type_identifier":
            text = n.text.decode("utf-8")
            out.append(text.rsplit(".", 1)[-1])
            continue
        # Descend into containers like type_list.
        stack.extend(n.children)
    return out


def _enclosing_class_or_interface(node: Any) -> Any:
    """Walk parents to find the nearest enclosing class_declaration or
    interface_declaration. Returns None if at file top level."""
    cur = node.parent
    while cur is not None:
        if cur.type in ("class_declaration", "interface_declaration"):
            return cur
        cur = cur.parent
    return None


def _enclosing_method(node: Any) -> Any:
    """Walk parents to find the nearest enclosing method_declaration or
    constructor_declaration. Returns None if not inside one."""
    cur = node.parent
    while cur is not None:
        if cur.type in ("method_declaration", "constructor_declaration"):
            return cur
        cur = cur.parent
    return None


def _infer_receiver_type(call_node: Any) -> str | None:
    """Try to infer the simple-name static type of the receiver of a
    method_invocation. Returns None on any uncertainty (fail-closed).

    Supported receiver shapes:
      - missing object (unqualified call inside class) -> enclosing class name
      - identifier            -> field lookup, then local variable / parameter lookup
      - field_access `this.x` -> identifier lookup on `x` (fields only)
    Other receiver shapes (method_invocation chain, cast, object_creation, etc.)
    return None.
    """
    obj = call_node.child_by_field_name("object")
    if obj is None:
        # Unqualified call inside a class — receiver type is the enclosing class.
        enclosing = _enclosing_class_or_interface(call_node)
        if enclosing is None:
            return None
        name_node = enclosing.child_by_field_name("name")
        return name_node.text.decode("utf-8") if name_node else None

    # Resolve a `this.x` field-access to a bare identifier `x`.
    if obj.type == "field_access":
        # `this.x` shape: object=`this`, field=`x`.
        inner_obj = obj.child_by_field_name("object")
        field = obj.child_by_field_name("field")
        if inner_obj is not None and inner_obj.type == "this" and field is not None:
            return _lookup_field_type(call_node, field.text.decode("utf-8"))
        return None

    if obj.type == "identifier":
        ident = obj.text.decode("utf-8")
        # Try locals/params first (innermost scope wins), then fields.
        local = _lookup_local_or_param_type(call_node, ident)
        if local is not None:
            return local
        return _lookup_field_type(call_node, ident)

    # Anything else — chained calls, casts, news, parenthesized — fail closed.
    return None


def _lookup_field_type(node: Any, ident: str) -> str | None:
    """Find a field_declaration named `ident` in the enclosing class. Returns
    its declared type's simple name (generics stripped), or None."""
    enclosing = _enclosing_class_or_interface(node)
    if enclosing is None:
        return None
    body = enclosing.child_by_field_name("body")
    if body is None:
        return None
    for ch in body.children:
        if ch.type != "field_declaration":
            continue
        type_node = ch.child_by_field_name("type")
        if type_node is None:
            continue
        for fc in ch.children:
            if fc.type == "variable_declarator":
                name_node = fc.child_by_field_name("name")
                if name_node is not None and name_node.text.decode("utf-8") == ident:
                    return _strip_generics(type_node.text.decode("utf-8"))
    return None


def _lookup_local_or_param_type(node: Any, ident: str) -> str | None:
    """Find a local_variable_declaration or formal_parameter named `ident` in
    the enclosing method. Returns the declared simple-name type, or None."""
    method = _enclosing_method(node)
    if method is None:
        return None
    # Formal parameters.
    params = method.child_by_field_name("parameters")
    if params is not None:
        for p in params.children:
            if p.type in ("formal_parameter", "spread_parameter"):
                pname = p.child_by_field_name("name")
                ptype = p.child_by_field_name("type")
                if pname is not None and ptype is not None and pname.text.decode("utf-8") == ident:
                    return _strip_generics(ptype.text.decode("utf-8"))
    # Local variables anywhere in the method body.
    body = method.child_by_field_name("body")
    if body is not None:
        for decl in _find_nodes(body, "local_variable_declaration"):
            type_node = decl.child_by_field_name("type")
            if type_node is None:
                continue
            for fc in decl.children:
                if fc.type == "variable_declarator":
                    name_node = fc.child_by_field_name("name")
                    if name_node is not None and name_node.text.decode("utf-8") == ident:
                        return _strip_generics(type_node.text.decode("utf-8"))
    return None


def _capture_argument(arg_node: Any, base: str) -> dict[str, str]:
    """Extract string / qualified-identifier / class-literal forms from a Java argument."""
    captures: dict[str, str] = {
        base: "",
        f"{base}_const": "",
        f"{base}_class": "",
        f"{base}_text": arg_node.text.decode("utf-8"),
    }
    if arg_node.type == "string_literal":
        # Pull the string_fragment child (no quotes).
        for ch in arg_node.children:
            if ch.type == "string_fragment":
                captures[base] = ch.text.decode("utf-8")
                break
    elif arg_node.type == "field_access":
        captures[f"{base}_const"] = arg_node.text.decode("utf-8")
    elif arg_node.type == "class_literal":
        for ch in arg_node.children:
            if ch.type == "type_identifier":
                captures[f"{base}_class"] = ch.text.decode("utf-8")
                break
    elif arg_node.type == "identifier":
        captures[f"{base}_const"] = arg_node.text.decode("utf-8")
    return captures


def _ts_class_supertype_typearg(
    lens: dict[str, Any],
    root: Any,
    rel: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    """Find classes that have a given generic supertype (extends OR implements)
    and capture one of its type arguments.

    Lens match.tree_sitter config:
      superclass:    str (required) — the supertype name to look for. Despite the
                     name (kept for back-compat with the legacy
                     `class-extends-typearg` extractor), this matches BOTH
                     `extends X<...>` (superclass) AND `implements X<...>`
                     (super_interfaces). Useful for Quarkus Panache repositories
                     declared as `class FooRepo implements PanacheRepository<Foo>`.
      typearg_index: int (default 0) — which type argument to capture
      capture_as:    str (default "aggregate") — capture group name

    The original `class-extends-typearg` extractor name is preserved as an alias
    that delegates here. Existing Eventuate-tram lens uses the legacy name with a
    `superclass` value (AbstractAggregateDomainEventPublisher) that only ever
    appears in `extends` position, so widening to also match `implements` is a
    strict superset and back-compatible.
    """
    from .engine import _emit_node

    match = lens["match"]
    emit = lens["emit"]
    ts_config = match.get("tree_sitter", {})
    target_super = ts_config.get("superclass")
    if not target_super:
        raise ValueError("class-supertype-typearg extractor requires tree_sitter.superclass")
    typearg_index = int(ts_config.get("typearg_index", 0))
    capture_as = ts_config.get("capture_as", "aggregate")

    nodes: list[Node] = []
    edges: list[Edge] = []

    for cls_node in _find_nodes(root, "class_declaration"):
        # Gather all generic_type nodes from the superclass and super_interfaces
        # clauses. Each candidate is a (name, type_arguments) pair.
        candidates: list[tuple[str, Any]] = []
        for ch in cls_node.children:
            if ch.type in ("superclass", "super_interfaces"):
                for gt in _find_generic_types_in_clause(ch):
                    name = ""
                    type_args = None
                    for inner in gt.children:
                        if inner.type == "type_identifier":
                            name = inner.text.decode("utf-8")
                        elif inner.type == "scoped_type_identifier":
                            name = inner.text.decode("utf-8").rsplit(".", 1)[-1]
                        elif inner.type == "type_arguments":
                            type_args = inner
                    if name and type_args is not None:
                        candidates.append((name, type_args))

        matched = None
        for name, type_args in candidates:
            if name == target_super:
                matched = type_args
                break
        if matched is None:
            continue

        typeargs = [c for c in matched.children if c.type not in ("<", ">", ",")]
        if typearg_index >= len(typeargs):
            continue
        arg = typeargs[typearg_index]
        class_name_node = cls_node.child_by_field_name("name")
        captures = {
            capture_as: arg.text.decode("utf-8"),
            "class_name": class_name_node.text.decode("utf-8") if class_name_node else "",
        }
        line_no = cls_node.start_point[0] + 1
        nodes.append(_emit_node(emit, captures, rel, line_no, service))

    return nodes, edges


def _find_generic_types_in_clause(clause: Any) -> list[Any]:
    """Walk a superclass / super_interfaces clause and collect every generic_type
    child (the `X<T>` shape). Non-generic supertypes (`extends X`) are ignored
    since this extractor requires a type argument to capture.
    """
    out: list[Any] = []
    stack = list(clause.children)
    while stack:
        n = stack.pop()
        if n.type == "generic_type":
            out.append(n)
            continue
        # super_interfaces wraps a `type_list`; descend into it but not into
        # generic_type bodies (we want top-level supertypes only).
        if n.type == "type_list":
            stack.extend(n.children)
    return out


def _ts_query(
    lens: dict[str, Any],
    language: Any,
    root: Any,
    rel: str,
    content: str,
    service: str,
) -> tuple[list[Node], list[Edge]]:
    """Run a tree-sitter Query against the parsed AST. Each match emits one node.

    Lens match.tree_sitter config:
      query:        str (required) — tree-sitter S-expression query string
      anchor:       str (optional) — name of a capture that anchors the emitted node
                    (line number and base for sibling-walks). Defaults to first capture.
      next_sibling: dict (optional) — for the anchor node, walk forward through its
                    siblings to find one with a matching type; expose data from it.
        type:           str (required) — sibling node type to find (e.g. "method_definition")
        skip_types:     list[str] (default: []) — sibling types to skip past
        captures:       dict[str, str] (required) — `capture_name: field_name` map
                        Use `text` as field_name for the node's full text.

    Captures from the query are available as template variables in `emit.values`.
    Captures from `next_sibling.captures` are also available.
    """
    from .engine import _emit_node

    match = lens["match"]
    emit = lens["emit"]
    ts_config = match.get("tree_sitter", {})
    query_str = ts_config.get("query")
    if not query_str:
        raise ValueError("query extractor requires tree_sitter.query")

    anchor = ts_config.get("anchor")
    sibling_cfg = ts_config.get("next_sibling", {})

    query = ts.Query(language, query_str)
    cursor = ts.QueryCursor(query)
    matches = cursor.matches(root)

    nodes: list[Node] = []
    edges: list[Edge] = []

    for _pat_idx, captures_map in matches:
        # Build a flat capture dict: capture_name -> text of first node.
        flat_captures: dict[str, str] = {}
        for cap_name, cap_nodes in captures_map.items():
            if cap_nodes:
                flat_captures[cap_name] = cap_nodes[0].text.decode("utf-8")

        # Pick the anchor node for positioning & sibling-walks.
        anchor_name = anchor or next(iter(captures_map.keys()), None)
        anchor_node = captures_map.get(anchor_name, [None])[0] if anchor_name else None
        if anchor_node is None:
            continue

        # Optional sibling walk.
        if sibling_cfg:
            sib = _walk_to_sibling(
                anchor_node,
                target_type=sibling_cfg.get("type", ""),
                skip_types=set(sibling_cfg.get("skip_types", [])),
            )
            if sib is not None:
                for cap_name, field_name in sibling_cfg.get("captures", {}).items():
                    if field_name == "text":
                        flat_captures[cap_name] = sib.text.decode("utf-8")
                    else:
                        f = sib.child_by_field_name(field_name)
                        if f:
                            flat_captures[cap_name] = f.text.decode("utf-8")
            elif sibling_cfg.get("required", True):
                # If sibling lookup was required and failed, skip this match.
                continue

        line_no = anchor_node.start_point[0] + 1
        nodes.append(_emit_node(emit, flat_captures, rel, line_no, service))

    return nodes, edges


def _walk_to_sibling(node: Any, target_type: str, skip_types: set[str]) -> Any:
    """Walk forward through a node's parent's children to find a sibling of target_type.

    Stops if a non-skip, non-target sibling is encountered.
    """
    parent = node.parent
    if parent is None:
        return None
    siblings = list(parent.children)
    try:
        idx = siblings.index(node)
    except ValueError:
        return None
    for s in siblings[idx + 1:]:
        if s.type == target_type:
            return s
        if s.type in skip_types:
            continue
        # An unexpected sibling type - stop.
        return None
    return None


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
