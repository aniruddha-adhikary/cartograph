"""Tree-sitter parsing with per-language parser cache."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from tree_sitter import Parser, Tree

from .languages import get_language


@lru_cache(maxsize=None)
def _parser_for(language_name: str) -> Parser:
    return Parser(get_language(language_name))


def parse_source(language_name: str, source: bytes) -> Tree:
    return _parser_for(language_name).parse(source)


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
