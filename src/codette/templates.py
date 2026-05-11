"""Mini template engine for `{capture[.attr]|filter|filter:arg}` placeholders."""
from __future__ import annotations

import os
import re
from typing import Any, Callable


class TemplateError(ValueError):
    pass


_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def _filter_upper(v: str, *_: str) -> str:
    return v.upper()


def _filter_lower(v: str, *_: str) -> str:
    return v.lower()


def _filter_unquote(v: str, *_: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"', "`"):
        return v[1:-1]
    return v


def _filter_strip_prefix(v: str, *args: str) -> str:
    if not args:
        return v
    p = args[0]
    return v[len(p):] if v.startswith(p) else v


def _filter_strip_suffix(v: str, *args: str) -> str:
    if not args:
        return v
    s = args[0]
    return v[:-len(s)] if s and v.endswith(s) else v


def _filter_default(v: str, *args: str) -> str:
    if v == "" or v is None:
        return args[0] if args else ""
    return v


def _filter_concat(v: str, *args: str) -> str:
    return v + (args[0] if args else "")


def _filter_basename(v: str, *_: str) -> str:
    return os.path.basename(v)


def _filter_dirname(v: str, *_: str) -> str:
    return os.path.dirname(v)


def _filter_regex_replace(v: str, *args: str) -> str:
    if len(args) < 2:
        raise TemplateError("regex_replace requires PAT and REP")
    pat, rep = args[0], args[1]
    return re.sub(pat, rep, v)


def _filter_first(v: Any, *_: str) -> str:
    if isinstance(v, list):
        return str(v[0]) if v else ""
    return str(v)


FILTERS: dict[str, Callable[..., str]] = {
    "upper": _filter_upper,
    "lower": _filter_lower,
    "unquote": _filter_unquote,
    "strip_prefix": _filter_strip_prefix,
    "strip_suffix": _filter_strip_suffix,
    "default": _filter_default,
    "concat": _filter_concat,
    "basename": _filter_basename,
    "dirname": _filter_dirname,
    "regex_replace": _filter_regex_replace,
    "first": _filter_first,
}


def _lookup_path(path: list[str], ctx: dict[str, Any], *, optional: bool) -> str:
    """Walk a dotted path like ['parent', 'class_name'] through nested dicts.

    If the final value is a dict with a 'text' key, auto-resolve to that text
    (so `{capture}` behaves like `{capture.text}` for tree-sitter captures).
    """
    val: Any = ctx
    for i, part in enumerate(path):
        if isinstance(val, dict):
            if part not in val:
                if optional:
                    return ""
                missing = ".".join(path[: i + 1])
                raise TemplateError(f"unknown placeholder {missing!r} in template")
            val = val[part]
        else:
            if optional:
                return ""
            joined = ".".join(path[:i])
            raise TemplateError(
                f"cannot access attribute {part!r} on non-object value at {joined!r}"
            )
    if isinstance(val, dict):
        return str(val.get("text", ""))
    return str(val)


def _apply_filters(value: str, filter_specs: list[str]) -> str:
    out = value
    for spec in filter_specs:
        if ":" in spec:
            fname, _, rest = spec.partition(":")
            args = rest.split(":")
        else:
            fname, args = spec, []
        if fname not in FILTERS:
            raise TemplateError(f"unknown filter {fname!r}")
        out = FILTERS[fname](out, *args)
    return out


def render(template: str, ctx: dict[str, Any]) -> str:
    """Render `template` against `ctx` (capture name → str or dict)."""
    def sub(m: re.Match[str]) -> str:
        body = m.group(1)
        parts = body.split("|")
        head = parts[0].strip()
        filter_specs = [p.strip() for p in parts[1:]]
        optional = head.endswith("?")
        if optional:
            head = head[:-1].strip()
        path = [p for p in head.split(".") if p]
        if not path:
            raise TemplateError(f"empty placeholder {m.group(0)!r}")
        value = _lookup_path(path, ctx, optional=optional)
        return _apply_filters(value, filter_specs)

    return _PLACEHOLDER_RE.sub(sub, template)
