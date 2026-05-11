from pathlib import Path

from codette.engine import Engine
from conftest import FIXTURES, PACKS


def _index(repo: str):
    engine = Engine.from_packs(PACKS)
    graph, _ = engine.index(FIXTURES / repo)
    return graph


def test_spring_emits_service_and_endpoints():
    g = _index("spring-mini")
    services = g.by_label("Service")
    endpoints = g.by_label("Endpoint")
    assert len(services) == 1
    assert services[0].properties["name"] == "UserController"
    assert services[0].properties["base_path"] == "/api/users"

    assert len(endpoints) == 2
    methods = sorted(e.properties["http_method"] for e in endpoints)
    assert methods == ["GET", "POST"]
    for e in endpoints:
        assert e.properties["base_path_ref"] == services[0].id


def test_spring_handles_edges():
    g = _index("spring-mini")
    service_id = g.by_label("Service")[0].id
    handles = [e for e in g.edges if e.type == "HANDLES"]
    assert len(handles) == 2
    for e in handles:
        assert e.from_id == service_id


def test_express_emits_endpoints_and_router_mount():
    g = _index("express-mini")
    endpoints = g.by_label("Endpoint")
    mounts = g.by_label("RouterMount")
    assert {e.properties["http_method"] for e in endpoints} == {"GET", "POST", "DELETE"}
    assert len(mounts) == 1
    assert mounts[0].properties["mount_path"] == "/api/v2"
    assert mounts[0].properties["child_router"] == "usersRouter"


def test_react_emits_components_and_calls():
    g = _index("react-mini")
    components = g.by_label("Component")
    calls = g.by_label("HttpCall")
    names = sorted(c.properties["name"] for c in components)
    assert names == ["App", "UserCard", "UserList"]
    kinds = {c.properties["name"]: c.properties["kind"] for c in components}
    assert kinds["App"] == "class"
    assert kinds["UserCard"] == "function"

    assert len(calls) == 1
    assert calls[0].properties["http_method"] == "GET"
    assert calls[0].properties["path"] == "/api/users"


def test_crosstier_emits_crosses_tier_edge():
    g = _index("crosstier-mini")
    crosses = [e for e in g.edges if e.type == "CROSSES_TIER"]
    assert len(crosses) == 2  # GET + POST fetches
    confidences = sorted(e.properties["confidence"] for e in crosses)
    assert confidences == ["high", "high"]


def test_provenance_fields_present():
    g = _index("spring-mini")
    n = g.by_label("Service")[0]
    p = n.properties["provenance"]
    assert p["pack"] == "spring"
    assert p["rule_id"] == "spring.rest-controller"
    assert p["engine_version"]


def test_deterministic_output():
    g1 = _index("crosstier-mini")
    g2 = _index("crosstier-mini")
    assert g1.to_json_str() == g2.to_json_str()
