from codette.graph import Edge, Graph, Node
from codette.linkers.http import HttpCrossTierLinker, normalize_template


def test_normalize_collapses_template_styles():
    assert normalize_template("/users/{id}") == normalize_template("/users/:id")
    assert normalize_template("/users/{id}") == normalize_template("/users/${id}")
    assert normalize_template("/users/{id}/posts/{pid}") == "/users/§/posts/§"


def test_normalize_strips_trailing_slash():
    assert normalize_template("/users/") == "/users"
    assert normalize_template("/") == "/"


def _endpoint(node_id: str, method: str, path: str, *, base_path: str = "", base_path_ref: str | None = None) -> Node:
    props = {
        "http_method": method,
        "path": path,
        "file": "x.java",
        "line": 1,
    }
    if base_path:
        props["base_path"] = base_path
    if base_path_ref:
        props["base_path_ref"] = base_path_ref
    return Node(id=node_id, label="Endpoint", properties=props)


def _service(node_id: str, base_path: str) -> Node:
    return Node(id=node_id, label="Service", properties={"base_path": base_path, "file": "x.java", "line": 1})


def _call(node_id: str, method: str, path: str) -> Node:
    return Node(id=node_id, label="HttpCall", properties={
        "http_method": method, "path": path, "file": "x.jsx", "line": 1,
    })


def test_literal_match_high_confidence():
    g = Graph()
    g.add_node(_endpoint("ep1", "GET", "/api/users"))
    g.add_node(_call("c1", "GET", "/api/users"))
    HttpCrossTierLinker().run(g)
    ct = [e for e in g.edges if e.type == "CROSSES_TIER"]
    assert len(ct) == 1
    assert ct[0].properties["confidence"] == "high"
    assert ct[0].from_id == "c1"
    assert ct[0].to_id == "ep1"


def test_template_match_medium_confidence():
    g = Graph()
    g.add_node(_endpoint("ep1", "GET", "/users/{id}"))
    g.add_node(_call("c1", "GET", "/users/:id"))
    HttpCrossTierLinker().run(g)
    ct = [e for e in g.edges if e.type == "CROSSES_TIER"]
    assert len(ct) == 1
    assert ct[0].properties["confidence"] == "medium"


def test_method_mismatch_no_edge():
    g = Graph()
    g.add_node(_endpoint("ep1", "GET", "/api/x"))
    g.add_node(_call("c1", "POST", "/api/x"))
    HttpCrossTierLinker().run(g)
    assert [e for e in g.edges if e.type == "CROSSES_TIER"] == []


def test_base_path_resolution():
    g = Graph()
    g.add_node(_service("svc1", "/api/users"))
    g.add_node(_endpoint("ep1", "GET", "/{id}", base_path_ref="svc1"))
    # Templated call aligned with templated endpoint
    g.add_node(_call("c1", "GET", "/api/users/${userId}"))
    HttpCrossTierLinker().run(g)
    ct = [e for e in g.edges if e.type == "CROSSES_TIER"]
    assert len(ct) == 1
    # Resolution stored back onto endpoint
    ep = g.get_node("ep1")
    assert ep.properties["absolute_path"] == "/api/users/{id}"
    # Both sides templated → medium confidence
    assert ct[0].properties["confidence"] == "medium"


def test_idempotent_run_does_not_duplicate():
    g = Graph()
    g.add_node(_endpoint("ep1", "GET", "/x"))
    g.add_node(_call("c1", "GET", "/x"))
    linker = HttpCrossTierLinker()
    linker.run(g)
    n_first = sum(1 for e in g.edges if e.type == "CROSSES_TIER")
    g.drop_edges_by_linker(linker.name)
    linker.run(g)
    n_second = sum(1 for e in g.edges if e.type == "CROSSES_TIER")
    assert n_first == n_second == 1
