"""Minimal tests for the new linker rules."""
from __future__ import annotations

from cartograph.graph import Graph
from cartograph.linkers import (
    link_cdi_event,
    link_endpoint_param,
    link_entity_relation,
    link_injection,
)


def _node(label: str, service: str = "svc", **props) -> dict:
    file = props.pop("file", f"{label}.java")
    line = props.pop("line", 1)
    base = {
        "id": f"{service}:{file}:{line}:{label}",
        "label": label,
        "service": service,
        "file": file,
        "line": line,
        "source": "lens:test",
        "confidence": "high",
    }
    base.update(props)
    return base


def test_link_injection_emits_injects_edge():
    g = Graph()
    inj = _node("Injection", target_class="Caller", injected_type="MyBean", kind="inject", file="Caller.java")
    comp = _node("Component", name="MyBean", file="MyBean.java", line=2,
                 id="svc:MyBean.java:2:comp")
    g.nodes.extend([inj, comp])
    link_injection(g)
    assert len(g.edges) == 1
    e = g.edges[0]
    assert e["type"] == "INJECTS"
    assert e["from"] == inj["id"]
    assert e["to"] == comp["id"]
    assert e["target_class"] == "Caller"
    assert e["injected_type"] == "MyBean"
    assert e["injection_kind"] == "inject"


def test_link_injection_prefers_same_service():
    g = Graph()
    inj = _node("Injection", service="a", target_class="C", injected_type="X", kind="inject")
    other = _node("Component", service="b", name="X", id="b:X.java:1:o")
    same = _node("Component", service="a", name="X", id="a:X.java:1:s")
    g.nodes.extend([inj, other, same])
    link_injection(g)
    assert len(g.edges) == 1
    assert g.edges[0]["to"] == same["id"]


def test_link_injection_persistence_context_emits_unit_edge():
    g = Graph()
    inj = _node("Injection", kind="persistence-context", injected_type="EntityManager",
                unit_name="myPU", target_class="DAO")
    unit = _node("PersistenceUnit", name="myPU", id="svc:pu.xml:1:u")
    comp = _node("Component", name="EntityManager", id="svc:em.java:1:c")
    g.nodes.extend([inj, unit, comp])
    link_injection(g)
    types = sorted(e["type"] for e in g.edges)
    assert "INJECTS" in types
    assert "USES_PERSISTENCE_UNIT" in types


def test_link_injection_unresolved_recorded():
    g = Graph()
    inj = _node("Injection", target_class="C", injected_type="Nothing", kind="inject")
    g.nodes.append(inj)
    link_injection(g)
    assert g.edges == []
    assert any(u["kind"] == "no_inject_target" for u in g.meta["unresolved"])


def test_link_entity_relation_emits_relates_to():
    g = Graph()
    rel = _node("EntityRelation", owner_class="Movie", target_type="List<Actor>",
                kind="OneToMany", field_name="actors")
    owner = _node("Entity", name="Movie", id="svc:Movie.java:1:o")
    target = _node("Entity", name="Actor", id="svc:Actor.java:1:t")
    g.nodes.extend([rel, owner, target])
    link_entity_relation(g)
    assert len(g.edges) == 1
    e = g.edges[0]
    assert e["type"] == "RELATES_TO"
    assert e["from"] == owner["id"]
    assert e["to"] == target["id"]
    assert e["kind"] == "OneToMany"
    assert e["field_name"] == "actors"


def test_link_entity_relation_unwraps_map_to_value_type():
    g = Graph()
    rel = _node("EntityRelation", owner_class="A", target_type="Map<String, B>",
                kind="OneToMany", field_name="items")
    owner = _node("Entity", name="A", id="svc:A.java:1:o")
    target = _node("Entity", name="B", id="svc:B.java:1:t")
    g.nodes.extend([rel, owner, target])
    link_entity_relation(g)
    assert len(g.edges) == 1
    assert g.edges[0]["to"] == target["id"]


def test_link_cdi_event_cartesian_pairs():
    g = Graph()
    p1 = _node("EventProducer", event_type="Greeting", owner_class="A")
    p2 = _node("EventProducer", event_type="Greeting", owner_class="B",
               id="svc:B.java:5:p2", line=5)
    c1 = _node("EventConsumer", event_type="Greeting", handler="X.h",
               id="svc:X.java:1:c1")
    c2 = _node("EventConsumer", event_type="Greeting", handler="Y.h",
               id="svc:Y.java:2:c2", line=2)
    g.nodes.extend([p1, p2, c1, c2])
    link_cdi_event(g)
    assert len(g.edges) == 4
    assert all(e["type"] == "EVENT_DELIVERS" and e["bus"] == "cdi-event" for e in g.edges)


def test_link_cdi_event_unresolved_when_no_consumer():
    g = Graph()
    p = _node("EventProducer", event_type="Lonely", owner_class="A")
    g.nodes.append(p)
    link_cdi_event(g)
    assert g.edges == []
    assert any(u["kind"] == "no_event_consumer" for u in g.meta["unresolved"])


def test_link_endpoint_param_matches_by_handler():
    g = Graph()
    ep = _node("Endpoint", handler="MyResource.list", path="/x",
               id="svc:r.java:1:e")
    p = _node("EndpointParam", owner_class="MyResource", owner_method="list",
              kind="QueryParam", name="page", id="svc:r.java:5:p", line=5)
    g.nodes.extend([ep, p])
    link_endpoint_param(g)
    assert len(g.edges) == 1
    e = g.edges[0]
    assert e["type"] == "HAS_PARAM"
    assert e["from"] == ep["id"]
    assert e["to"] == p["id"]
    assert e["kind"] == "QueryParam"
    assert e["name"] == "page"


def test_link_endpoint_param_unresolved_when_no_endpoint():
    g = Graph()
    p = _node("EndpointParam", owner_class="MissingResource", owner_method="x", kind="path", name="y")
    g.nodes.append(p)
    link_endpoint_param(g)
    assert g.edges == []
    assert any(u["kind"] == "no_endpoint_for_param" for u in g.meta["unresolved"])
