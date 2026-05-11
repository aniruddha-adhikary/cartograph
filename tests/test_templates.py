import pytest

from codette.templates import TemplateError, render


def _cap(text: str, start_line: int = 1) -> dict:
    return {"text": text, "start_line": start_line, "end_line": start_line}


def test_basic_capture_auto_text():
    assert render("Hello {name}", {"name": _cap("World")}) == "Hello World"


def test_attribute_access():
    assert render("{name.start_line}", {"name": _cap("x", 42)}) == "42"


def test_filters_chain():
    assert render("{x|upper}", {"x": _cap("foo")}) == "FOO"
    assert render("{x|unquote}", {"x": _cap('"bar"')}) == "bar"
    assert render("{x|strip_prefix:/}", {"x": _cap("/api/users")}) == "api/users"
    assert render("{x|strip_suffix:.js}", {"x": _cap("server.js")}) == "server"
    assert render("{x|basename}", {"x": _cap("/a/b/c.txt")}) == "c.txt"
    assert render("{x|dirname}", {"x": _cap("/a/b/c.txt")}) == "/a/b"
    assert render("{x|regex_replace:_:-}", {"x": _cap("a_b_c")}) == "a-b-c"


def test_default_filter():
    assert render("{x|default:none}", {"x": _cap("")}) == "none"
    assert render("{x|default:none}", {"x": _cap("ok")}) == "ok"


def test_concat_filter():
    assert render("{x|concat:.suffix}", {"x": _cap("base")}) == "base.suffix"


def test_optional_placeholder_missing():
    assert render("[{missing?}]", {}) == "[]"
    assert render("[{missing?|upper}]", {}) == "[]"
    assert render("[{missing?|default:fallback}]", {}) == "[fallback]"


def test_required_placeholder_missing_raises():
    with pytest.raises(TemplateError):
        render("[{absent}]", {})


def test_nested_path():
    ctx = {"parent": {"this": {"id": "abc123"}, "class_name": _cap("UserController")}}
    assert render("{parent.this.id}", ctx) == "abc123"
    assert render("{parent.class_name}", ctx) == "UserController"


def test_unknown_filter_errors():
    with pytest.raises(TemplateError):
        render("{x|bogus}", {"x": _cap("y")})
