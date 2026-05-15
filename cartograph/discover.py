from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+)|^\s*const\s+\w+\s*=\s*require\(['\"]([^'\"]+)['\"]\)")


def discover_pack_candidates(workspace: Path) -> dict[str, Any]:
    imports: Counter[str] = Counter()
    annotations: Counter[str] = Counter()
    calls: Counter[str] = Counter()
    files_scanned = 0

    for path in workspace.rglob("*"):
        if not path.is_file() or path.suffix not in {".java", ".js", ".ts", ".tsx"}:
            continue
        if any(part in {"target", "build", "dist", "node_modules", "src/test", "__tests__"} for part in path.parts):
            continue
        files_scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            m = IMPORT_RE.search(line)
            if m:
                imports[(m.group(1) or m.group(2)).split(".")[0]] += 1
            for annotation in re.findall(r"@\w+", line):
                annotations[annotation] += 1
            for call in re.findall(r"\.(\w+)\s*\(", line):
                calls[call] += 1

    return {
        "files_scanned": files_scanned,
        "top_import_roots": imports.most_common(30),
        "top_annotations": annotations.most_common(30),
        "top_method_calls": calls.most_common(30),
        "candidate_pack_overlay": candidate_overlay(imports, annotations, calls),
        "llm_instruction": (
            "Use this discovery JSON plus 3-5 representative files to produce a reviewed "
            ".cartograph/packs/<language>.json overlay. Do not modify extractor code. "
            "Only add framework tokens, annotations, mapping names, message bus definitions, and client call tokens "
            "that are supported by the pack schema."
        ),
    }


def candidate_overlay(imports: Counter[str], annotations: Counter[str], calls: Counter[str]) -> dict[str, Any]:
    overlay: dict[str, Any] = defaultdict(dict)
    http_tokens = [
        f".{name}("
        for name, _ in calls.most_common()
        if name.lower() in {"uri", "retrieve", "exchange", "getforobject", "postforentity"}
    ]
    if http_tokens:
        overlay["spring"]["http_clients"] = {"tokens": sorted(set(http_tokens))}
    controller_annotations = [
        name
        for name, _ in annotations.most_common()
        if name.endswith("Controller") or name in {"@RestController", "@Controller"}
    ]
    if controller_annotations:
        overlay["spring"]["rest"] = {"controller_annotations": sorted(set(controller_annotations))}
    if "KafkaListener" in "".join(annotations):
        overlay["spring"]["message_buses"] = [
            {
                "name": "kafka",
                "listener_annotation": "@KafkaListener",
            }
        ]
    if imports.get("express") or calls.get("Router"):
        overlay["javascript"]["express"] = {"app_tokens": ["express()", "Router()"]}
    return dict(overlay)


def write_discovery(workspace: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(discover_pack_candidates(workspace), indent=2, sort_keys=True) + "\n", encoding="utf-8")
