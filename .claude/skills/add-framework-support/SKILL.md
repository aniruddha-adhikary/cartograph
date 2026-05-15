---
name: add-framework-support
description: "Use this skill ANYTIME you're about to add Cartograph support for a new framework, library, message bus, RPC system, or annotation convention — Spring, Kafka, Express, Fastify, Eventuate, gRPC, NATS, Mongoose, Sequelize, anything. Also trigger on phrases like 'make cartograph understand X', 'add a lens for Y', 'extract Z annotations', 'recognize this new pattern in code'. The first instinct is almost always wrong — this skill prevents the lens-first design contract from being violated."
---

# Adding Framework Support to Cartograph

Cartograph splits framework knowledge (JSON lenses) from extraction machinery (Python engine). Every time a new framework is added, the temptation is to edit `cartograph/engine.py`, `cartograph/linkers.py`, or `cartograph/tree_sitter_strategy.py` to "just handle this one pattern". That's the wrong answer almost every time, and it's how this codebase accumulates spaghetti.

Use this skill to add support the right way.

## The contract

| What you're adding | Where it goes |
|---|---|
| Recognize a framework's annotations / call patterns / channels | `cartograph/lens_defs/<framework>.json` (built-in) or `.cartograph/lenses/<framework>.json` (project-local) |
| Map raw captured values to clean fields | `scope: resolve` lens in the same place |
| Express a graph-shape query over already-indexed data | `scope: graph` lens |
| Add a generic extraction primitive (e.g., "match all class declarations with a given supertype") | New strategy in `cartograph/engine.py` or `cartograph/tree_sitter_strategy.py` — but only after exhausting existing strategies and confirming the primitive is useful for >1 framework |

**You almost never need that fourth row.** The existing strategies — `regex`, `annotation-method`, `token-line`, `xml-element`, `config-key`, `tree-sitter` — cover virtually every framework pattern in practice.

## The workflow

### 1. Identify the patterns in source

Before opening any editor, read a few real examples of the framework's idioms in actual source code (use a real repo if possible; `.cartograph-real-repos/` already has Spring, PiggyMetrics, FTGO). Write down:

- The class/method-level annotations or decorators
- Which arguments carry the "important" values (path, topic, channel, queue name)
- The shape of producer/consumer markers (`@SomethingListener`, `.send(...)`, `.subscribe(...)`, `extends BaseX<T>`)
- Any naming conventions for constants that hold channel/topic names

### 2. Pick the right strategy

| Pattern shape | Strategy |
|---|---|
| One-line decorator or annotation with a string argument | `regex` with `per_line: true` |
| Class-level annotation + method-level annotations binding routes | `annotation-method` |
| Method call with literal-string arg (`app.get('/foo', ...)`, `.send("topic", ...)`) | `token-line` with `extract` regex |
| XML element with attribute capture | `xml-element` |
| Property/YAML key with value | `config-key` |
| Anything Java/JS/TS that needs structural matching (multi-line fluent builders, generic-typed superclasses, method calls with non-literal args like `Foo.CONSTANT`) | `tree-sitter` |

When in doubt, prefer `tree-sitter` for any non-trivial Java/JS pattern. Regex breaks on whitespace, line breaks, generics, and fluent builders. AST doesn't.

### 3. Write the lens JSON

Drop a new file in `cartograph/lens_defs/<framework>.json` (or `.cartograph/lenses/` for project-local). Read existing lenses in the same directory for examples — `spring-rest-endpoint.json`, `spring-feign.json`, `eventuate-tram.json`, `kafkajs.json`, `express-routes.json` cover most shapes.

Every lens needs: `name`, `scope`, `match` (with `files`, `strategy`, and strategy-specific config), and `emit` (label, schema, values, source, confidence).

### 4. Test against fixtures

Add or extend a fixture in `fixtures/` with a minimal source file exercising the pattern. Run the engine on it directly to confirm extraction:

```bash
python -c "
from cartograph.engine import run_source_lens
from cartograph.lens_schema import load_lens_file
from pathlib import Path
lens = load_lens_file(Path('cartograph/lens_defs/<framework>.json'))[0]  # or by name
content = Path('fixtures/<fixture>.java').read_text()
nodes, edges = run_source_lens(lens, '<fixture>.java', content, 'svc')
for n in nodes: print(n.to_dict())
"
```

### 5. Index a real repo

```bash
python -m cartograph index --workspace .cartograph-real-repos/<repo> --out /tmp/g.json
```

Read the stdout summary. The tool prints `meta.unresolved` for every gap the linker couldn't close. If your new lens produced nodes but the linker can't connect them to anything, the unresolved list tells you what's missing — usually a `service-registry.yaml` entry, a `resolve-hints.json` patch, or a companion lens for the consumer side.

### 6. Validate tests still pass

```bash
python -m pytest tests/ -q
```

If you had to regen any golden snapshot files, that's expected after adding new lenses.

### 7. Update reference docs (only if you added a new strategy)

If you added a NEW strategy to the engine (rare — see "When you actually need engine code" below), update `.apm/skills/cartograph/references/lens-authoring.md` so future authors know it exists.

## What if regex isn't enough?

Symptoms:
- The pattern spans multiple lines (e.g., fluent builders, multi-line annotations)
- The argument is a constant reference (`Foo.CHANNEL_NAME`) not a string literal
- Generics get in the way (`extends Publisher<X, Y>`)

Solution: use `strategy: tree-sitter` with one of the existing extractors:

- `annotation-method` — class + method annotations
- `walk` — find any AST node type and capture fields from it
- `method-call` — find method invocations by name, capture first arg (handles string/`Foo.BAR`/`X.class`)
- `class-extends-typearg` — find classes extending a named generic superclass, capture a type argument

If none of these fit, the right move is to add a **generic** extractor — one that any future framework could use. NOT one that hardcodes your framework's names. See the next section.

## When you actually need engine code

You may need to touch Python if and only if all three apply:

1. The pattern is not expressible with any existing strategy
2. The new primitive you'd add is generic — at least one other framework would plausibly use it
3. The primitive does not name a specific framework, library, annotation, or protocol in Python

If you can't satisfy all three, stop and write the lens differently. If you can, the lens-discipline-guard hook will still scan the change for framework tokens — that's expected; clean primitives pass.

## Anti-patterns (will be blocked or reviewed)

- Adding `if framework_name in line:` checks to `engine.py` or `linkers.py`
- Hardcoding regex like `r"@FeignClient\("` in Python (belongs in a lens's `match.patterns`)
- Adding URL/JDBC/AMQP parsing to `linkers.py` (use a `resolve` lens)
- Naming a helper after a framework (`_handle_kafka_listener`, `_parse_feign_args`)
- Re-introducing the dead pack system (`packs_dir`, `discover_packs`, `controller_annotations`)

The `.claude/hooks/lens_discipline.py` hook blocks edits to engine files that introduce these tokens. The `lens-discipline-reviewer` subagent catches subtler shape-violations the hook misses.

## After you finish

Re-index every real repo affected and check the unresolved list shrinks. If it doesn't, the lens isn't matching what you expected — debug at the regex/AST level, not in Python.

```bash
python -m cartograph index --workspace .cartograph-real-repos/spring-petclinic-microservices --out /tmp/petclinic.json
python -m cartograph index --workspace .cartograph-real-repos/piggymetrics --out /tmp/piggymetrics.json
python -m cartograph index --workspace .cartograph-real-repos/ftgo-application --out /tmp/ftgo.json
```

Report the before/after edge counts and unresolved counts. That's the success metric — a working lens reduces unresolved gaps and increases edges. Code that increases line count in `cartograph/*.py` but doesn't reduce unresolved is the wrong shape.
