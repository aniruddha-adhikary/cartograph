# Cartograph Refinement Loop

When a query returns a thin graph (few edges, lots of nodes), the linker couldn't connect things on its own. This is normal and expected — real codebases reference services via runtime-injected env vars, dynamic discovery clients, framework-specific naming conventions, etc. The tool surfaces every gap on `graph.meta.unresolved` so you can investigate and patch.

This document is the operating manual for closing those gaps.

## The contract

After `cartograph index`, look at:

```bash
jq '.meta.unresolved' cartograph-out/graph.json
```

Each entry is one of:

```json
{
  "kind": "unresolved_host",
  "node_id": "service:file:line:hash",
  "service": "calling-service",
  "host_slug": "",
  "raw": {"url": "http://customers-service/owners", "feign_args": "..."},
  "hint": "HttpCall has references {...} but no service matched slug '...'",
  "known_services": ["...", "..."]
}
```

```json
{
  "kind": "no_consumer",
  "node_id": "...",
  "service": "producer-service",
  "topic": "{unknown}",
  "bus": "kafka",
  "hint": "Producer publishes to '...' but no consumer subscribes to it"
}
```

`raw` is the actual data the lens captured. `known_services` lists what's available to match against. The hint tells you in plain English what failed.

## Three mechanisms to close gaps

Always try them in this order — cheapest first.

### 1. `service-registry.yaml` (preferred)

When the gap is "the host name in the code doesn't match the service directory name" — which is most cross-service HTTP cases. Spring Cloud uses logical service names from Eureka. Docker Compose uses short hostnames. Feign uses a `name = "..."` attribute. Your services are named after the directories they live in.

Put a `service-registry.yaml` at the workspace root:

```yaml
# Logical name : actual service directory name
customers-service: spring-petclinic-customers-service
visits-service: spring-petclinic-visits-service
auth-service: auth-service
statistics-service: statistics-service

# External APIs
rates-client: external:exchangeratesapi
```

The format is flat `key: value` per line. The linker slugifies both sides and matches.

When to use: the raw value (host, host_var, feign_args) contains a recognisable name that maps 1:1 to a service.

### 2. `resolve` lens (for repeatable patterns)

When the gap is "the host is buried inside an opaque captured string and I'd need to extract it the same way every time" — URLs need host/path split, Feign annotations need name-attribute extraction, JDBC URLs need host+port+db split.

Add a JSON file under `.cartograph/lenses/`:

```json
[
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
]
```

This runs on every HttpCall node post-index, before the linker. Built-in resolve lenses already handle common HTTP/Feign cases — if your need is more exotic (custom RPC framework, custom annotation), add one. See lens-authoring.md for the full shape.

When to use: the gap is general — many nodes share the same parsing problem.

### 3. `resolve-hints.json` (for one-off patches)

When the gap is "the value the lens captured can't be parsed to derive the host because the host is only known at runtime via an env var or config injection". Common in API gateways where routes are configured via `@ConfigurationProperties` bound to environment variables.

Put a `resolve-hints.json` at the workspace root:

```json
[
  {
    "match": {"label": "HttpCall", "service": "ftgo-api-gateway", "url": "/consumers"},
    "set": {"host": "ftgo-consumer-service"}
  },
  {
    "match": {"label": "HttpCall", "service": "ftgo-api-gateway", "url": "/orders/{orderId}"},
    "set": {"host": "ftgo-order-service"}
  },
  {
    "match": {"label": "HttpCall", "service": "ftgo-api-gateway-graphql", "host_var": "this.consumerService"},
    "set": {"host": "ftgo-consumer-service"}
  }
]
```

`match` is an exact equality dict — every key in `match` must equal the corresponding field on the node. `set` overwrites or sets the listed fields.

When to use:
- The lens captured a path-only URL because the host comes from an env var
- The node references an instance variable that points to a service URL constructed at runtime
- A truly one-off mapping that doesn't generalise

`graph.meta.resolve_hints_applied` reports how many patches were applied — verify your hint matched something.

---

## A worked example

Scenario: indexed PiggyMetrics, got 0 edges, 4 unresolved entries.

**Step 1.** Read `meta.unresolved`:

```json
{
  "kind": "unresolved_host",
  "service": "account-service",
  "host_slug": "",
  "raw": {"feign_args": "name = \"auth-service\""},
  "hint": "...",
  "known_services": ["account-service", "auth-service", ...]
}
```

**Step 2.** Open the source file at the cited line. Confirm it's a `@FeignClient(name = "auth-service")` declaration.

**Step 3.** Choose mechanism. The Feign name `auth-service` matches a known service `auth-service` exactly. A `resolve` lens that extracts the `name` attribute from `feign_args` into `host` would generalise. We already have one built-in. So all we need is `service-registry.yaml`:

```yaml
auth-service: auth-service
statistics-service: statistics-service
account-service: account-service
notification-service: notification-service
rates-client: external:exchangeratesapi
```

**Step 4.** Re-index. Edges go from 0 to 3, unresolved goes to 0.

---

## Heuristics for picking the mechanism

| Situation | Use |
|---|---|
| Hostname in code differs from service directory name, 1:1 mapping | service-registry.yaml |
| Same parsing rule applies to many nodes (URL split, Feign name extraction) | resolve lens |
| Specific node has no extractable identifier — host is set at runtime | resolve-hints.json |
| Many nodes need different specific patches | combine resolve-hints with a script that generates them |
| New framework with no built-in lens at all | source lens first, then check what's still unresolved |

## When you can't resolve at all

Some patterns are genuinely beyond static analysis:
- Dynamic service discovery where the target is computed from external state
- Message buses that use class names as topics (Eventuate Tram uses aggregate FQCN)
- Plugin-based architectures where handlers are registered at runtime

For these, either:
1. Write a `source` lens that captures the framework-specific shape (e.g., a lens that recognises `AbstractAggregateDomainEventPublisher<X, ...>` and uses `X` as the topic)
2. Document the gap as a known limitation in the service's `cartograph.yaml`
3. Use `resolve-hints.json` to encode what a human reader would conclude

The goal isn't 100% automatic coverage. The goal is that every gap is visible, structured, and patchable.
