"""YAML rule pack loader + schema validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from tree_sitter import Query, QueryError

from .languages import SUPPORTED_LANGUAGES, get_language


class PackError(ValueError):
    pass


@dataclass
class Emit:
    kind: str  # "node" | "edge"
    spec: dict[str, Any]


@dataclass
class Rule:
    id: str
    pack: str
    description: str
    language: str
    imports_any: list[str]
    file_glob: str | None
    query_str: str
    where: dict[str, dict[str, Any]]
    body_contains: list[str]
    emits: list[Emit]
    sub_rules: list["Rule"]
    source_file: str
    _query: Query | None = field(default=None, repr=False)

    @property
    def query(self) -> Query:
        if self._query is None:
            raise PackError(f"rule {self.id}: query not compiled")
        return self._query


@dataclass
class Pack:
    name: str
    path: Path
    rules: list[Rule]


_REQUIRED_RULE_KEYS = ("id", "when", "match", "emit")
_REQUIRED_WHEN_KEYS = ("language",)


def _ensure(condition: bool, msg: str) -> None:
    if not condition:
        raise PackError(msg)


def _parse_emit(emit_specs: list[Any], rule_id: str) -> list[Emit]:
    out: list[Emit] = []
    _ensure(isinstance(emit_specs, list), f"rule {rule_id}: emit must be a list")
    for i, item in enumerate(emit_specs):
        _ensure(isinstance(item, dict), f"rule {rule_id}: emit[{i}] must be a mapping")
        keys = list(item.keys())
        _ensure(len(keys) == 1, f"rule {rule_id}: emit[{i}] must have exactly one key (node|edge)")
        kind = keys[0]
        _ensure(kind in ("node", "edge"), f"rule {rule_id}: emit[{i}] unknown kind {kind!r}")
        spec = item[kind]
        _ensure(isinstance(spec, dict), f"rule {rule_id}: emit[{i}].{kind} must be a mapping")
        if kind == "node":
            _ensure("label" in spec, f"rule {rule_id}: emit[{i}].node missing 'label'")
            _ensure("id" in spec, f"rule {rule_id}: emit[{i}].node missing 'id' template")
        else:
            for k in ("type", "from", "to"):
                _ensure(k in spec, f"rule {rule_id}: emit[{i}].edge missing {k!r}")
        out.append(Emit(kind=kind, spec=spec))
    return out


def _parse_rule(raw: dict[str, Any], pack_name: str, source_file: str) -> Rule:
    for k in _REQUIRED_RULE_KEYS:
        _ensure(k in raw, f"rule in {source_file}: missing key {k!r}")
    rule_id = raw["id"]
    _ensure(isinstance(rule_id, str) and rule_id, f"rule in {source_file}: 'id' must be a non-empty string")
    when = raw["when"]
    _ensure(isinstance(when, dict), f"rule {rule_id}: 'when' must be a mapping")
    for k in _REQUIRED_WHEN_KEYS:
        _ensure(k in when, f"rule {rule_id}: when.{k} required")
    language = when["language"]
    _ensure(language in SUPPORTED_LANGUAGES,
            f"rule {rule_id}: unsupported language {language!r} (allowed: {SUPPORTED_LANGUAGES})")
    imports_any = list(when.get("imports_any") or [])
    file_glob = when.get("file_glob")
    match = raw["match"]
    _ensure(isinstance(match, dict) and "query" in match,
            f"rule {rule_id}: 'match.query' required")
    query_str = match["query"]
    _ensure(isinstance(query_str, str) and query_str.strip(),
            f"rule {rule_id}: 'match.query' must be a non-empty string")
    where = match.get("where") or {}
    _ensure(isinstance(where, dict), f"rule {rule_id}: 'match.where' must be a mapping")
    body_contains = match.get("body_contains") or []
    _ensure(isinstance(body_contains, list),
            f"rule {rule_id}: 'match.body_contains' must be a list")
    emits = _parse_emit(raw["emit"], rule_id)
    sub_rules_raw = raw.get("sub_rules") or []
    _ensure(isinstance(sub_rules_raw, list), f"rule {rule_id}: 'sub_rules' must be a list")
    sub_rules: list[Rule] = []
    for sr in sub_rules_raw:
        sr = dict(sr)
        # Sub-rules inherit language from parent if not specified
        sr.setdefault("when", {})
        sr["when"].setdefault("language", language)
        sub_rules.append(_parse_rule(sr, pack_name, source_file))
    rule = Rule(
        id=rule_id,
        pack=pack_name,
        description=raw.get("description", ""),
        language=language,
        imports_any=imports_any,
        file_glob=file_glob,
        query_str=query_str,
        where=where,
        body_contains=list(body_contains),
        emits=emits,
        sub_rules=sub_rules,
        source_file=source_file,
    )
    # Compile query now to surface tree-sitter errors at load time.
    try:
        rule._query = Query(get_language(language), query_str)
    except QueryError as exc:
        raise PackError(
            f"rule {rule_id} in {source_file}: query compile failed: {exc}"
        ) from exc
    return rule


def load_pack(yaml_path: Path) -> Pack:
    text = yaml_path.read_text()
    pack_name = yaml_path.parent.name
    raw_docs = list(yaml.safe_load_all(text))
    rules: list[Rule] = []
    for doc in raw_docs:
        if doc is None:
            continue
        _ensure(isinstance(doc, dict), f"{yaml_path}: top-level YAML must be a mapping")
        rules.append(_parse_rule(doc, pack_name, str(yaml_path)))
    return Pack(name=pack_name, path=yaml_path, rules=rules)


def load_packs(packs_dir: Path) -> list[Pack]:
    if not packs_dir.exists():
        raise PackError(f"packs directory does not exist: {packs_dir}")
    packs: list[Pack] = []
    for yaml_path in sorted(packs_dir.rglob("*.yaml")):
        packs.append(load_pack(yaml_path))
    for yaml_path in sorted(packs_dir.rglob("*.yml")):
        packs.append(load_pack(yaml_path))
    return packs
