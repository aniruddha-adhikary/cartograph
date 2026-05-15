from __future__ import annotations

import json
import re
import shutil
from importlib import resources
from pathlib import Path

AGENTS_MARKER = "## cartograph"
AGENTS_SECTION = """\
## cartograph
This project can maintain a Cartograph graph at `cartograph-out/`.

Rules:
- Before answering architecture, flow, endpoint, Kafka, or cross-service questions, read `cartograph-out/GRAPH_REPORT.md` if it exists.
- Prefer Cartograph CLI tools over raw text search for service-flow questions. Run `cartograph tools` to discover available tools.
- Use `cartograph flow`, `cartograph search`, `cartograph endpoints-in-service`, `cartograph cross-service-edges`, `cartograph kafka-topics`, `cartograph coverage-report`, and `cartograph lens` for graph questions.
- When asked "what happens when X runs?", start with `cartograph explain --graph cartograph-out/graph.json --anchor <X>`.
- When asked "who calls X?", run `cartograph find-callers --graph cartograph-out/graph.json --symbol <X>`.
- When asked "what does service S expose?", run `cartograph endpoints-in-service --graph cartograph-out/graph.json --service <S>`.
- When asked "which topics/events reach S?", run `cartograph kafka-topics --graph cartograph-out/graph.json --consumer-service <S>`.
- When asked "where should I edit?", run `cartograph search --graph cartograph-out/graph.json --query <terms>` before broad text search.
- Lenses are raw Kuzu Cypher projections over the typed property graph. For task-specific or domain-specific concepts, create or update `.cartograph/lenses/*.json` with `kind: "query"` and run `cartograph lens --graph cartograph-out/graph.json --name <lens> --workspace .`.
- Run `cartograph lens list --graph cartograph-out/graph.json --workspace .` before creating a new project lens.
- Do not invent lens operator DSLs. Express higher-level abstraction directly in the Kuzu query with `MATCH`, shared variables, `WHERE`, and `RETURN`.
- Use `cartograph serve --graph cartograph-out/graph.json` only when a long-running JSON-lines tool bridge is useful.
- Use raw source reads when editing/debugging specific code or when the graph lacks the needed detail.
- After modifying service code, run `cartograph index --workspace . --out cartograph-out/graph.json --report cartograph-out/GRAPH_REPORT.md` to refresh the graph.
- For project-specific framework wrappers, run `cartograph discover-packs --workspace . --out .cartograph/discovery.json` and add reviewed overlays under `.cartograph/packs/`; do not patch extractor code for one repo.
- For project-specific graph questions, add `.cartograph/lenses/*.json` lens specs, `.cartograph/views/*.json` view specs, or explicit `.cartograph/plugins/*.py` plugins and invoke them with `cartograph lens`, `cartograph query --name <view>`, or reviewed `cartograph run-plugin --allow-plugin`.
"""

CLAUDE_SECTION = AGENTS_SECTION

CODEX_HOOK = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            'python3 -c "import json,pathlib,sys; '
                            "data=json.load(sys.stdin); cmd=data.get('tool_input',data).get('cmd','') or data.get('tool_input',data).get('command',''); "
                            "hit=pathlib.Path('cartograph-out/graph.json').exists() and any(x in cmd for x in ['rg ', 'grep ', 'find ', 'fd ']); "
                            "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', "
                            "'additionalContext': 'Cartograph graph exists. Read cartograph-out/GRAPH_REPORT.md or run cartograph tools and use Cartograph CLI queries before broad source search.'}}) if hit else '{}')\""
                        ),
                    }
                ],
            }
        ]
    }
}


def install(platform: str, project_dir: Path) -> list[Path]:
    project_dir = project_dir.resolve()
    written: list[Path] = []
    if platform not in {"codex", "claude"}:
        raise ValueError("platform must be 'codex' or 'claude'")

    skill_name = "skill-codex.md" if platform == "codex" else "skill-claude.md"
    skill_dst = project_dir / (
        ".agents/skills/cartograph/SKILL.md" if platform == "codex" else ".claude/skills/cartograph/SKILL.md"
    )
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    with resources.files("cartograph").joinpath(f"skills/{skill_name}").open("rb") as src:
        with skill_dst.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    written.append(skill_dst)

    if platform == "codex":
        agents = project_dir / "AGENTS.md"
        upsert_section(agents, AGENTS_SECTION)
        written.append(agents)
        hooks = project_dir / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True, exist_ok=True)
        hooks.write_text(json.dumps(CODEX_HOOK, indent=2) + "\n", encoding="utf-8")
        written.append(hooks)
    else:
        claude = project_dir / "CLAUDE.md"
        upsert_section(claude, CLAUDE_SECTION)
        written.append(claude)

    return written


def uninstall(platform: str, project_dir: Path) -> list[Path]:
    project_dir = project_dir.resolve()
    removed: list[Path] = []
    skill_dst = project_dir / (
        ".agents/skills/cartograph/SKILL.md" if platform == "codex" else ".claude/skills/cartograph/SKILL.md"
    )
    if skill_dst.exists():
        skill_dst.unlink()
        removed.append(skill_dst)
    target = project_dir / ("AGENTS.md" if platform == "codex" else "CLAUDE.md")
    if target.exists() and AGENTS_MARKER in target.read_text(encoding="utf-8"):
        remove_section(target)
        removed.append(target)
    hooks = project_dir / ".codex/hooks.json"
    if platform == "codex" and hooks.exists():
        hooks.unlink()
        removed.append(hooks)
    return removed


def upsert_section(path: Path, section: str) -> None:
    if path.exists():
        content = path.read_text(encoding="utf-8")
        if AGENTS_MARKER in content:
            content = (
                re.sub(
                    r"\n*## cartograph\n.*?(?=\n## |\Z)", "\n\n" + section.rstrip(), content, flags=re.DOTALL
                ).rstrip()
                + "\n"
            )
        else:
            content = content.rstrip() + "\n\n" + section
    else:
        content = section
    path.write_text(content, encoding="utf-8")


def remove_section(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    cleaned = re.sub(r"\n*## cartograph\n.*?(?=\n## |\Z)", "", content, flags=re.DOTALL).rstrip()
    if cleaned:
        path.write_text(cleaned + "\n", encoding="utf-8")
    else:
        path.unlink()
