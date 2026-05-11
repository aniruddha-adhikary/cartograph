# codette graph JSON schema

The CLI emits a JSON document with two top-level arrays: `nodes` and `edges`.
Output is **deterministic**: nodes are sorted by `id`, edges are sorted by
`(type, from_id, to_id)`. No timestamps are emitted.

## Node

```jsonc
{
  "id": "0d322cf52f93b8ad",       // 16-hex content hash, stable across reindex
  "label": "Endpoint",             // semantic node type
  "properties": {
    "file": "backend/server.js",   // repo-relative path
    "line": 5,                     // 1-indexed start line of anchor node
    "line_end": 5,                 // 1-indexed end line
    "confidence": "high",          // "high" | "medium" | "low"
    "framework": "express",        // pack-defined
    "http_method": "POST",
    "path": "/api/users",
    "absolute_path": "/api/users", // populated by HTTP linker for Endpoints
    "provenance": {
      "pack": "express",
      "rule_id": "express.endpoint",
      "engine_version": "0.1.0"
    }
    // additional pack-specific keys
  }
}
```

## Edge

```jsonc
{
  "type": "CROSSES_TIER",          // HANDLES | CROSSES_TIER | CALLS | ...
  "from_id": "1d98833d2cae7bff",
  "to_id": "afe430413c43d56c",
  "properties": {
    "confidence": "high",
    "matched_method": "GET",        // linker-specific
    "matched_path": "/api/users",
    "provenance": {                 // for linker-emitted edges
      "linker": "http_cross_tier",
      "engine_version": "0.1.0"
    }
  }
}
```

## Built-in node labels (Stage 1)

| Label        | Emitted by    | Purpose                                                |
|--------------|---------------|--------------------------------------------------------|
| `Service`    | spring        | A REST controller class                                |
| `Endpoint`   | spring, express | An HTTP endpoint                                     |
| `RouterMount`| express       | `app.use('/prefix', router)`                           |
| `Component`  | react         | A React function or class component                    |
| `HttpCall`   | react         | A `fetch()` or `axios.<verb>()` call site              |

## Built-in edge types (Stage 1)

| Type           | Emitted by      | Direction                       |
|----------------|-----------------|---------------------------------|
| `HANDLES`      | spring (rule)   | `Service` → `Endpoint`          |
| `CROSSES_TIER` | http linker     | `HttpCall` → `Endpoint`         |

## Stable IDs

```
id = sha1(rule_id + "::" + file_relpath + "::" + canonical_text + "::" + line_start)[:16]
```

Where `canonical_text` is the rendered `id` template from the rule, with
whitespace normalized. Including `rule_id` prevents collisions when two rules
emit on the same span; including `line_start` survives most refactors.
