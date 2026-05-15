from __future__ import annotations

from cartograph.engine import run_source_lens
from cartograph.lens_schema import load_builtin_lenses


def test_load_builtin_lenses_returns_all_definitions() -> None:
    lenses = load_builtin_lenses()
    names = [l["name"] for l in lenses]
    assert "spring-rest-endpoint" in names
    assert "express-routes" in names
    assert "struts-action-node" in names
    assert "sql-mapper" in names
    assert "spring-kafka-consumer" in names
    assert len(lenses) >= 10


def test_builtin_spring_rest_lens_extracts_endpoints() -> None:
    lenses = load_builtin_lenses()
    lens = next(l for l in lenses if l["name"] == "spring-rest-endpoint")
    content = """@RestController
@RequestMapping("/api/users")
class UserController {
    @GetMapping("/{id}")
    public User getUser() { return null; }

    @PostMapping
    public User createUser() { return null; }
}"""
    nodes, edges = run_source_lens(lens, "UserController.java", content, service="user-svc")
    assert len(nodes) == 2
    assert nodes[0].get("http_method") == "GET"
    assert nodes[0].get("path") == "/api/users/{id}"
    assert nodes[0].get("handler") == "UserController.getUser"
    assert nodes[1].get("http_method") == "POST"


def test_builtin_express_lens_extracts_routes() -> None:
    lenses = load_builtin_lenses()
    lens = next(l for l in lenses if l["name"] == "express-routes")
    content = """const app = express();
app.get('/users', listUsers);
app.post('/users', createUser);
"""
    nodes, edges = run_source_lens(lens, "routes.js", content, service="web")
    assert len(nodes) == 2
    assert nodes[0].get("http_method") == "get"
    assert nodes[0].get("path") == "/users"


def test_builtin_struts_lens_extracts_actions() -> None:
    lenses = load_builtin_lenses()
    lens = next(l for l in lenses if l["name"] == "struts-action-node")
    content = """<struts>
  <package name="default" namespace="/admin">
    <action name="listUsers" class="com.example.UserAction" method="list">
      <result>/WEB-INF/views/users.jsp</result>
    </action>
  </package>
</struts>"""
    nodes, edges = run_source_lens(lens, "struts.xml", content, service="legacy")
    assert len(nodes) == 1
    assert nodes[0].get("name") == "listUsers"


def test_builtin_sql_mapper_lens_extracts_queries() -> None:
    lenses = load_builtin_lenses()
    lens = next(l for l in lenses if l["name"] == "sql-mapper")
    content = """<mapper namespace="com.example.UserMapper">
  <select id="findById" resultType="User">
    SELECT * FROM users WHERE id = #{id}
  </select>
  <insert id="createUser">
    INSERT INTO users (name) VALUES (#{name})
  </insert>
</mapper>"""
    nodes, edges = run_source_lens(lens, "UserMapper.xml", content, service="user-svc")
    assert len(nodes) == 2
    assert nodes[0].get("operation") == "SELECT"
    assert nodes[0].get("query_id") == "findById"
    assert nodes[1].get("operation") == "INSERT"


def test_builtin_spring_config_lens_extracts_app_name() -> None:
    lenses = load_builtin_lenses()
    lens = next(l for l in lenses if l["name"] == "spring-config")
    content = "server.port=8080\nspring.application.name=order-service\n"
    nodes, edges = run_source_lens(lens, "application.properties", content, service="orders")
    assert len(nodes) == 1
    assert nodes[0].get("value") == "order-service"


def test_builtin_kafka_producer_lens_extracts_topic() -> None:
    lenses = load_builtin_lenses()
    lens = next(l for l in lenses if l["name"] == "spring-kafka-producer")
    content = 'kafkaTemplate.send("order-events", payload);'
    nodes, edges = run_source_lens(lens, "OrderService.java", content, service="orders")
    assert len(nodes) == 1
    assert nodes[0].get("topic") == "order-events"
