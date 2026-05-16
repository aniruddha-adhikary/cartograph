"""A5: ancestor-walk selectors in `xml-query` strategy."""
from cartograph.engine import run_source_lens


MYBATIS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="org.example.AccountMapper">
  <select id="getAccountByUsername" resultType="Account">
    SELECT * FROM ACCOUNT WHERE USERID = #{username}
  </select>
  <select id="getAccountByUsernameAndPassword" resultType="Account">
    SELECT * FROM ACCOUNT WHERE USERID = #{username} AND PASSWD = #{password}
  </select>
  <insert id="insertAccount">
    INSERT INTO ACCOUNT VALUES (#{username})
  </insert>
</mapper>
"""


def _lens(captures):
    return {
        "match": {
            "strategy": "xml-query",
            "select": ".//select",
            "captures": captures,
        },
        "emit": {
            "label": "DatabaseQuery",
            "source": "lens:test",
            "values": {
                "id": "{{id}}",
                "namespace": "{{namespace}}",
                "result_type": "{{result_type}}",
            },
        },
    }


def test_caret_attr_captures_parent_attribute():
    lens = _lens({
        "id": "@id",
        "result_type": "@resultType",
        "namespace": "^@namespace",
    })
    nodes, _ = run_source_lens(lens, "AccountMapper.xml", MYBATIS_XML, "petstore")
    assert len(nodes) == 2
    for n in nodes:
        assert n.props["namespace"] == "org.example.AccountMapper"
    ids = {n.props["id"] for n in nodes}
    assert ids == {"getAccountByUsername", "getAccountByUsernameAndPassword"}


def test_double_caret_climbs_two_levels():
    doc = """<root>
  <outer name="O">
    <middle>
      <leaf id="L1"/>
      <leaf id="L2"/>
    </middle>
  </outer>
</root>"""
    lens = {
        "match": {
            "strategy": "xml-query",
            "select": ".//leaf",
            "captures": {"id": "@id", "outer_name": "^^@name"},
        },
        "emit": {
            "label": "X",
            "source": "lens:test",
            "values": {"id": "{{id}}", "outer_name": "{{outer_name}}"},
        },
    }
    nodes, _ = run_source_lens(lens, "x.xml", doc, "svc")
    assert len(nodes) == 2
    assert all(n.props["outer_name"] == "O" for n in nodes)


def test_dotdot_slash_form_equivalent_to_caret():
    lens = _lens({
        "id": "@id",
        "namespace": "../@namespace",
    })
    # `../@namespace` peels one parent then captures attribute.
    nodes, _ = run_source_lens(lens, "AccountMapper.xml", MYBATIS_XML, "petstore")
    for n in nodes:
        assert n.props["namespace"] == "org.example.AccountMapper"


def test_caret_slash_tag_descends_from_parent():
    doc = """<root>
  <group label="G1">
    <meta>hello</meta>
    <item id="i1"/>
    <item id="i2"/>
  </group>
</root>"""
    lens = {
        "match": {
            "strategy": "xml-query",
            "select": ".//item",
            "captures": {"id": "@id", "meta": "^/meta"},
        },
        "emit": {
            "label": "X",
            "source": "lens:test",
            "values": {"id": "{{id}}", "meta": "{{meta}}"},
        },
    }
    nodes, _ = run_source_lens(lens, "x.xml", doc, "svc")
    assert len(nodes) == 2
    assert all(n.props["meta"] == "hello" for n in nodes)


def test_backwards_compat_existing_selectors_still_work():
    lens = _lens({
        "id": "@id",
        "result_type": "@resultType",
    })
    nodes, _ = run_source_lens(lens, "AccountMapper.xml", MYBATIS_XML, "petstore")
    assert {n.props["id"] for n in nodes} == {
        "getAccountByUsername",
        "getAccountByUsernameAndPassword",
    }
