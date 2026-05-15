#!/usr/bin/env python3
"""PreToolUse hook that blocks framework-specific code in cartograph engine files.

Cartograph's design splits framework knowledge from engine code: every framework
(Spring, Kafka, Feign, Eventuate, Express, etc.) must be expressed as a JSON lens
in cartograph/lens_defs/ or .cartograph/lenses/, NOT as Python code in the engine,
linker, or tree-sitter strategy modules.

This hook reads the Edit/Write tool input from stdin and refuses the operation
when it detects framework-specific tokens being added to engine code paths.

The hook is permissive by default: it only fires on changes to a small allowlist
of "engine" Python files. Edits to lens JSON, tests, fixtures, and CLI code are
not gated.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Engine files: framework-agnostic infrastructure only.
ENGINE_PATHS = {
    "cartograph/engine.py",
    "cartograph/linkers.py",
    "cartograph/tree_sitter_strategy.py",
    "cartograph/lens_runner.py",
}

# Framework / library tokens that indicate domain knowledge leaking into engine code.
# A match is suspicious — these names belong in lens JSON, not Python.
FRAMEWORK_TOKENS = [
    # Java frameworks
    r"\bSpring(?!Boot starter)\w*",
    r"@RestController", r"@Controller", r"@RequestMapping",
    r"@GetMapping", r"@PostMapping", r"@PutMapping", r"@DeleteMapping", r"@PatchMapping",
    r"@FeignClient", r"@KafkaListener", r"@Document", r"@Query",
    r"\bFeign\w*", r"\bKafkaTemplate\b", r"\bKafkaListener\b",
    r"\bEventuate\w*", r"\bAbstractAggregateDomainEventPublisher\b",
    r"\bSagaCommandHandlersBuilder\b", r"\bDomainEventHandlersBuilder\b",
    r"\bRestTemplate\b", r"\bWebClient\b",
    # JS/TS frameworks
    r"\bExpress(?!ion)\w*", r"\bkafkajs\b", r"\bfastify\b",
    # Legacy frameworks
    r"\bStruts\w*", r"\bIbatis\b", r"\bMyBatis\b",
    # Message buses
    r"\bRabbitMQ\b", r"\bAMQP\b", r"\bSQS\b",
    # Specific protocol prefixes
    r'"jdbc:', r'"amqp://', r'"redis://', r'"mongodb://',
]

# Old pack-system tokens that should never reappear.
DEAD_TOKENS = [
    r"\bpacks_dir\b", r"\bdiscover_packs\b", r"\bcontroller_annotations\b",
    r"\bproducer_methods\b", r"\blistener_annotation\b", r"\bmessage_buses\b",
]


def _engine_file(path: str) -> bool:
    posix = path.replace("\\", "/")
    return any(posix.endswith(suffix) for suffix in ENGINE_PATHS)


def _scan(content: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            hits.append(match.group(0))
    return sorted(set(hits))


def _read_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _proposed_content(tool: str, tool_input: dict) -> str:
    if tool == "Write":
        return tool_input.get("content", "")
    if tool == "Edit":
        return tool_input.get("new_string", "")
    return ""


def main() -> int:
    payload = _read_input()
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool not in {"Edit", "Write"}:
        return 0

    file_path = tool_input.get("file_path", "")
    if not file_path or not _engine_file(file_path):
        return 0

    proposed = _proposed_content(tool, tool_input)
    if not proposed:
        return 0

    framework_hits = _scan(proposed, FRAMEWORK_TOKENS)
    dead_hits = _scan(proposed, DEAD_TOKENS)

    if not framework_hits and not dead_hits:
        return 0

    rel = file_path
    try:
        rel = str(Path(file_path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        pass

    msg = [
        f"lens-discipline-guard: blocked write to {rel}",
        "",
        "Engine files must stay framework-agnostic. The following tokens belong in JSON",
        "lens definitions (cartograph/lens_defs/*.json or .cartograph/lenses/*.json),",
        "not in Python code:",
        "",
    ]
    if framework_hits:
        msg.append(f"  Framework-specific: {', '.join(framework_hits)}")
    if dead_hits:
        msg.append(f"  Dead-system (old pack model): {', '.join(dead_hits)}")
    msg.extend([
        "",
        "If you genuinely need a NEW generic strategy (not a new framework), express",
        "it as a generic primitive — e.g., add a tree-sitter Query strategy rather",
        "than hardcoded node-type checks for one framework's grammar.",
        "",
        "Override (rare): set CARTOGRAPH_LENS_GUARD=off to bypass.",
    ])

    import os
    if os.environ.get("CARTOGRAPH_LENS_GUARD", "").lower() == "off":
        return 0

    print("\n".join(msg), file=sys.stderr)
    return 2  # PreToolUse: exit 2 blocks the tool call and surfaces stderr to Claude


if __name__ == "__main__":
    sys.exit(main())
