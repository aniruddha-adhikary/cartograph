# Cartograph Config Schemas

Cartograph validates pack and view config at load time. Invalid config fails before indexing or querying.

## Pack Overlay

Pack overlays live under `.cartograph/packs/*.json` or any layer's `packs/` directory. They are deep-merged over bundled packs.

Example:

```json
{
  "rest": {
    "controller_annotations": ["@RestController", "@MyCompanyController"],
    "base_mapping_annotation": "@RequestMapping",
    "method_mappings": {
      "Get": "GET",
      "Post": "POST"
    }
  },
  "message_buses": [
    {
      "name": "kafka",
      "listener_annotation": "@KafkaListener",
      "producer_methods": [".send(", ".publish("],
      "config_annotation": "@Value",
      "producer_label": "KafkaProducer",
      "consumer_label": "KafkaConsumer",
      "consumer_class_label": "KafkaConsumerClass",
      "handler_edge": "HANDLES_KAFKA",
      "delivery_edge": "KAFKA_DELIVERS",
      "source": "pack:spring-kafka",
      "config_source": "pack:spring-kafka-config"
    }
  ],
  "http_clients": {
    "tokens": ["RestTemplate", ".uri(", ".exchange("],
    "webclient_token": ".uri("
  },
  "gateway": {
    "uri_prefix": "lb://",
    "path_predicate": "Path",
    "strip_prefix_filter": "StripPrefix"
  }
}
```

Required shapes:

- Top-level sections are objects.
- `rest.controller_annotations` is a list.
- `rest.method_mappings` maps annotation prefixes to HTTP methods.
- `message_buses` is a list of named bus definitions. Each bus supplies listener annotation, producer method tokens, emitted labels, handler edge, delivery edge, and source strings.
- Legacy `kafka` overlays are still accepted and normalized into the `message_buses` shape.
- `http_clients.tokens` is a list of client-call tokens.
- Gateway values are non-empty strings.
- List-valued overlay fields append unique values by default. Named object lists, such as `message_buses`, merge by `name`.
- `struts`, `j2ee`, and `database` sections configure legacy Java XML and SQL extraction labels/sources without requiring framework-specific CLI commands.

## View Spec

View specs live under `.cartograph/views/*.json` or any layer's `views/` directory.

### Node View

```json
{
  "endpoints": {
    "kind": "nodes",
    "label": "Endpoint",
    "where": {"service": "$service"},
    "sort": ["service", "path"]
  }
}
```

Run:

```bash
cartograph query --graph cartograph-out/graph.json --name endpoints --param service=permits-api
```

### Edge View

```json
{
  "medium-confidence-crossings": {
    "kind": "edges",
    "cross_repo": true,
    "where": {"confidence": "medium"},
    "sort": ["from_service", "to_service", "type"]
  }
}
```

### Grouped Edge View

```json
{
  "message-topics": {
    "kind": "group_edges",
    "edge_type": "KAFKA_DELIVERS",
    "group_by": {"side": "from", "property": "topic"},
    "fields": {
      "publishers": {"side": "from", "property": "service"},
      "subscribers": {"side": "to", "property": "service"}
    }
  }
}
```

Required shapes:

- `kind` is `nodes`, `edges`, or `group_edges`.
- `where` is an object.
- `sort` is a list.
- `group_edges.group_by.side` and field sides are `from` or `to`.
- `group_edges.*.property` values are non-empty strings.

## Lens Spec

Lens specs live under `.cartograph/lenses/*.json` or any layer's `lenses/` directory. Authored lenses are raw Kuzu Cypher projections over the typed property graph.

```json
{
  "project.checkout-db-flow": {
    "kind": "query",
    "language": "kuzu-cypher",
    "returns": {
      "call": "HttpCall",
      "edge": "CROSSES_TIER",
      "route": "Endpoint",
      "lens": "Lens"
    },
    "query": [
      "MATCH (call:HttpCall)-[edge:CROSSES_TIER]->(route:Endpoint)",
      "OPTIONAL MATCH (lens:Lens)-[contains:CONTAINS]->(route:Endpoint)",
      "WHERE route.path CONTAINS 'checkout'",
      "RETURN call, edge, route, lens"
    ]
  }
}
```

Run:

```bash
cartograph lens --graph cartograph-out/graph.json --name project.checkout-db-flow --workspace .
```

Required shapes:

- `kind` must be `query`.
- `language` defaults to `kuzu-cypher`; if present it must be `kuzu-cypher`.
- `query` is a non-empty Kuzu Cypher string or list of query lines.
- `returns` maps returned variables to expected node labels or relationship types.
- `params` is an optional object for `$param` values in `WHERE`.
- Current CLI evaluation validates labels and relationship types against the graph and supports the query subset used by checked-in lenses: `MATCH`, `OPTIONAL MATCH`, `WHERE` with `CONTAINS`/`STARTS WITH`/`ENDS WITH`/`=`, and `RETURN`.

## Plugins

Plugins are not schema files. They are explicit local Python files with:

```python
def run(graph, args):
    return {"result": len(graph["nodes"])}
```

They run only through:

```bash
cartograph run-plugin --allow-plugin --graph cartograph-out/graph.json --plugin .cartograph/plugins/example.py
```

## Service Config

Each indexed service can include a `cartograph.yaml` file:

```yaml
name: permits-api
exclude:
  - src/generated/**
include_test_paths: false
```

- `name` sets the service id used in graph nodes and edges.
- `exclude`, `excludes`, and `additional_excludes` add file glob patterns on top of the core exclusion list.
- `include_test_paths: true` disables the default exclusion gate for that service.
