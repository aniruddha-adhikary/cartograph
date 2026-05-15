# Authoring Cartograph Lenses

All extraction and graph projection in Cartograph is lens-driven. There is no hardcoded Python rule for "this is a Spring controller" — that rule lives in `cartograph/lens_defs/spring-rest-endpoint.json`. Same for Kafka, Express, Struts, SQL mappers, Eventuate, Feign, MongoDB, etc.

Project-specific lenses live in `.cartograph/lenses/*.json` and are picked up via `--lens-dir .cartograph/lenses`. Project lenses extend (and can override by name) the built-in ones.

## The three lens scopes

| Scope | Purpose | Runs on | Produces |
|---|---|---|---|
| `source` | Extract nodes/edges from source files | individual files | `Node`, `Edge` |
| `resolve` | Parse raw fields on existing nodes into structured fields | the indexed node list | mutated node fields |
| `graph` | Run a Cypher-style query against the full graph | the indexed graph | a result set |

Pick the smallest scope that fits. If you can do it with `resolve`, don't reach for `source`. If you can do it with a `graph` lens, don't write a Python query function.

---

## 1. `source` lenses — extract from files

### Shape

```json
{
  "name": "my-framework-endpoint",
  "scope": "source",
  "match": {
    "files": ["*.java"],
    "strategy": "annotation-method",
    "class_annotations": ["@MyController"],
    "base_path_annotation": "@RequestMapping",
    "method_annotations": {"Get": "GET", "Post": "POST"}
  },
  "emit": {
    "label": "Endpoint",
    "schema": {"http_method": "string", "path": "string", "handler": "string"},
    "values": {
      "http_method": "{{http_method}}",
      "path": "{{path}}",
      "handler": "{{class_name}}.{{method_name}}"
    },
    "source": "lens:my-framework",
    "confidence": "high"
  }
}
```

### Strategies

| Strategy | Use for | Key match fields |
|---|---|---|
| `regex` | Generic pattern matching, single line or multi-line | `patterns: [{regex, per_line}]` |
| `annotation-method` | Java/Kotlin annotation-on-class with method-level mapping annotations | `class_annotations`, `base_path_annotation`, `method_annotations` |
| `token-line` | One-line patterns like `app.get('/users', ...)` or `kafkaTemplate.send("topic", ...)` | `tokens: [...]`, optional `extract: "regex"` |
| `xml-element` | Match XML elements by tag with attribute capture | `tag: "action"` (supports `\|` alternation), `attrs: [...]` |
| `config-key` | Properties/YAML key-value pairs | `key_pattern: "regex with named groups"` |
| `tree-sitter` | Structural AST parsing for Java/JS — handles complex annotation forms | `extractor: "annotation-method" \| "walk"` |

### Template captures

Values in `emit.values` use `{{name}}` interpolation. Available captures:
- Named groups from the matching regex (`(?P<name>...)`)
- Strategy-provided captures: `class_name`, `method_name`, `path`, `base_path`, `method_path`, `http_method`
- Meta: `_file_stem`, `_line`

Templates support a default fallback: `{{http_method|GET}}` resolves to `GET` when `http_method` isn't captured.

List values resolve element-by-element: `"topics": ["{{topic}}"]` becomes `["orders.created"]`.

### When to write a new `source` lens

Index a real repo, find unrecognized framework patterns (annotations, decorators, calls), and add a lens that captures the same shape as built-ins. Built-in examples in `cartograph/lens_defs/` are the best reference:

- `spring-rest-endpoint.json` — annotation-method
- `spring-feign.json` — regex on `@FeignClient(...)`
- `eventuate-tram.json` — three regex patterns (publisher, command handler, saga channel)
- `kafkajs.json` — token-line on `producer.send(...)` and `consumer.subscribe(...)`
- `struts-action.json` — xml-element on `<action>`

---

## 2. `resolve` lenses — enrich existing nodes

A `source` lens emits a node with whatever raw fields it captured. A `resolve` lens looks at that node afterwards and extracts more structured fields from one of those raw values using a regex.

Example: the `js-http-call-url` source lens captures `url=http://customers-service/owners/{id}`. The linker needs `host=customers-service` and `path=/owners/{id}` separately. A resolve lens splits them:

```json
{
  "name": "resolve-url-host",
  "scope": "resolve",
  "match": {
    "label": "HttpCall",
    "field": "url",
    "pattern": "^https?://(?P<host>[^/:]+)(?::\\d+)?(?P<path>/.*)$"
  },
  "set": {
    "host": "{{host}}",
    "path": "{{path}}"
  }
}
```

### When to use

- The same raw field across many nodes needs the same parsing (URL → host+path, JDBC URL → host+port+db, AMQP URL → broker+vhost+queue)
- You'd otherwise duplicate the parsing in every `source` lens

### When NOT to use

- The fix is one-off for a specific node — use `resolve-hints.json` (see refinement-loop reference)
- You need to set a value that isn't derivable from existing node fields — use a hint

---

## 3. `graph` lenses — query the indexed graph

```json
{
  "project.permits-cross-tier": {
    "kind": "query",
    "language": "kuzu-cypher",
    "returns": {
      "caller": "HttpCall",
      "edge": "CROSSES_TIER",
      "target": "Endpoint"
    },
    "query": [
      "MATCH (caller:HttpCall)-[edge:CROSSES_TIER]->(target:Endpoint)",
      "WHERE target.service = $service",
      "RETURN caller, edge, target"
    ]
  }
}
```

### Rules

- Use `kind: "query"` and `language: "kuzu-cypher"`
- Declare `returns` as a name → label/edge-type map (used by the renderer)
- Use `$param` placeholders, pass values via `--params '{"service": "permits-api"}'`
- Use `OPTIONAL MATCH` for nullable edges (e.g., route → mapper → query → table)

### When to use

- Repeatable, parameterised queries you want named and discoverable via `cartograph lens list`
- Project-specific terminology ("the order-fulfilment flow", "the permits domain")
- Anything you'd otherwise write as a one-off Python query

---

## Iteration cycle

1. Add the lens JSON to `.cartograph/lenses/`
2. `cartograph index --workspace . --lens-dir .cartograph/lenses --out cartograph-out/graph.json`
3. Query the graph or grep for the new nodes to confirm
4. If nothing matches, run `python -c "from cartograph.engine import run_source_lens; ..."` directly on a known-good file to debug the regex/strategy in isolation
5. Once it works, re-index the whole workspace and verify the unresolved list shrinks

---

## Anti-patterns

- **Don't patch Python for one framework's vocabulary.** Add a lens.
- **Don't write a `resolve` lens for a single specific node.** Use `resolve-hints.json`.
- **Don't write a regex that catches everything and then filter in `emit`.** Make the match precise.
- **Don't duplicate built-in lenses.** Project lenses with the same `name` as a built-in override it — use this deliberately, not accidentally.
