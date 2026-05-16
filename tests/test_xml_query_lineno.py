"""A6: per-element line numbers + full body extraction in `xml-query`."""
from cartograph.engine import run_source_lens


def test_each_matching_element_gets_distinct_line():
    doc = """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="ns">
  <select id="a">SELECT 1</select>
  <select id="b">SELECT 2</select>
  <select id="c">SELECT 3</select>
</mapper>
"""
    lens = {
        "match": {
            "strategy": "xml-query",
            "select": ".//select",
            "captures": {"id": "@id"},
        },
        "emit": {
            "label": "Q",
            "source": "lens:test",
            "values": {"id": "{{id}}"},
        },
    }
    nodes, _ = run_source_lens(lens, "m.xml", doc, "svc")
    assert len(nodes) == 3
    by_id = {n.props["id"]: n.line for n in nodes}
    # Lines: header is 1, <mapper> is 2, <select id=a> is 3, b is 4, c is 5.
    assert by_id["a"] == 3
    assert by_id["b"] == 4
    assert by_id["c"] == 5
    assert len(set(by_id.values())) == 3


def test_body_capture_includes_descendant_and_tail_text():
    """MyBatis dynamic SQL: trailing text after a child must be preserved."""
    doc = """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="ns">
  <select id="dyn">SELECT * FROM t WHERE <if test="x">x = 1</if> ORDER BY id</select>
</mapper>
"""
    lens = {
        "match": {
            "strategy": "xml-query",
            "select": ".//select",
            "captures": {"id": "@id", "body": "."},
        },
        "emit": {
            "label": "Q",
            "source": "lens:test",
            "values": {"id": "{{id}}", "body": "{{body}}"},
        },
    }
    nodes, _ = run_source_lens(lens, "m.xml", doc, "svc")
    assert len(nodes) == 1
    body = nodes[0].props["body"]
    assert "SELECT * FROM t WHERE" in body
    assert "x = 1" in body
    assert "ORDER BY id" in body
