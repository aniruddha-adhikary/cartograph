"""Top-level Engine: load packs, walk repo, execute rules, run linkers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .executor import ExecutionMetrics, execute_rule
from .graph import Graph
from .languages import language_for_path
from .linkers import HttpCrossTierLinker
from .pack import Pack, Rule, load_packs
from .parser import parse_source, read_bytes


@dataclass
class IndexReport:
    files_indexed: int = 0
    nodes_emitted: int = 0
    edges_emitted: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    per_pack: dict[str, ExecutionMetrics] = field(default_factory=dict)
    wall_ms: float = 0.0

    @property
    def all_packs_failed(self) -> bool:
        return self.nodes_emitted == 0 and any(m.errors > 0 for m in self.per_pack.values())


class Engine:
    def __init__(self, packs: list[Pack]) -> None:
        self.packs = packs
        self._rules_by_lang: dict[str, list[Rule]] = {}
        for pack in packs:
            for rule in pack.rules:
                self._rules_by_lang.setdefault(rule.language, []).append(rule)

    @classmethod
    def from_packs(cls, packs_dir: str | Path) -> "Engine":
        return cls(load_packs(Path(packs_dir)))

    @property
    def all_rules(self) -> list[Rule]:
        out: list[Rule] = []
        for pack in self.packs:
            out.extend(pack.rules)
        return out

    def _walk_files(self, repo: Path) -> list[Path]:
        skip = {".git", "node_modules", "__pycache__", "dist", "build", "target", ".venv", "venv"}
        out: list[Path] = []
        for path in sorted(repo.rglob("*")):
            if not path.is_file():
                continue
            if any(part in skip for part in path.parts):
                continue
            if language_for_path(path.name) is None:
                continue
            out.append(path)
        return out

    def index(
        self,
        repo: str | Path,
        *,
        changed_files: Iterable[str] | None = None,
        existing_graph: Graph | None = None,
    ) -> tuple[Graph, IndexReport]:
        repo = Path(repo).resolve()
        report = IndexReport()
        started = time.perf_counter()

        if existing_graph is not None and changed_files is not None:
            graph = existing_graph
            rel_changed = {self._normalize_rel(repo, p) for p in changed_files}
            graph.drop_nodes_from_files(rel_changed)
            files_to_process = [repo / r for r in rel_changed if (repo / r).exists()]
        else:
            graph = Graph()
            files_to_process = self._walk_files(repo)

        per_pack: dict[str, ExecutionMetrics] = {p.name: ExecutionMetrics() for p in self.packs}

        for file_path in files_to_process:
            lang = language_for_path(file_path.name)
            if lang is None:
                continue
            try:
                source = read_bytes(file_path)
            except OSError as exc:
                report.errors.append({
                    "pack": "-", "rule_id": "-", "file": str(file_path),
                    "error": f"read failed: {exc}",
                })
                continue

            applicable = self._rules_for_language(lang)
            if not applicable:
                continue

            file_relpath = str(file_path.relative_to(repo))
            try:
                tree = parse_source(lang, source)
            except Exception as exc:
                report.errors.append({
                    "pack": "-", "rule_id": "-", "file": file_relpath,
                    "error": f"parse failed: {exc}",
                })
                continue

            from .executor import _file_matches_when  # local import: hot path
            for rule in applicable:
                if not _file_matches_when(rule, lang, file_relpath, source):
                    continue
                metrics = per_pack[rule.pack]
                metrics.files_matched += 1
                execute_rule(
                    rule=rule,
                    root=tree.root_node,
                    file_relpath=file_relpath,
                    graph=graph,
                    metrics=metrics,
                    errors_sink=report.errors,
                )

            report.files_indexed += 1

        # Re-run linkers on full graph (drop linker-owned edges first to avoid duplication)
        for linker in self._default_linkers():
            graph.drop_edges_by_linker(linker.name)
            linker.run(graph)

        report.per_pack = per_pack
        report.nodes_emitted = len(graph.nodes)
        report.edges_emitted = len(graph.edges)
        report.wall_ms = (time.perf_counter() - started) * 1000.0
        return graph, report

    def _rules_for_language(self, lang: str) -> list[Rule]:
        rules = list(self._rules_by_lang.get(lang, []))
        # JSX is parsed as javascript; rules can target either.
        # TSX is its own grammar so we don't fold it.
        return rules

    def _default_linkers(self) -> list:
        return [HttpCrossTierLinker()]

    @staticmethod
    def _normalize_rel(repo: Path, p: str) -> str:
        path = Path(p)
        if path.is_absolute():
            try:
                return str(path.resolve().relative_to(repo))
            except ValueError:
                return str(path)
        return str(path)
