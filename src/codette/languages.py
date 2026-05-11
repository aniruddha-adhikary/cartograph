"""Language registry: extension → language name, and language name → ts Language."""
from __future__ import annotations

from functools import lru_cache

from tree_sitter import Language

_EXT_TO_LANG: dict[str, str] = {
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".py": "python",
    ".go": "go",
    ".cs": "c_sharp",
}

SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "java",
    "javascript",
    "typescript",
    "tsx",
    "python",
    "go",
    "c_sharp",
)


def language_for_path(path: str) -> str | None:
    for ext, lang in _EXT_TO_LANG.items():
        if path.endswith(ext):
            return lang
    return None


@lru_cache(maxsize=None)
def get_language(name: str) -> Language:
    if name == "java":
        import tree_sitter_java as m
        return Language(m.language())
    if name == "javascript":
        import tree_sitter_javascript as m
        return Language(m.language())
    if name == "typescript":
        import tree_sitter_typescript as m
        return Language(m.language_typescript())
    if name == "tsx":
        import tree_sitter_typescript as m
        return Language(m.language_tsx())
    if name == "python":
        import tree_sitter_python as m
        return Language(m.language())
    if name == "go":
        import tree_sitter_go as m
        return Language(m.language())
    if name == "c_sharp":
        import tree_sitter_c_sharp as m
        return Language(m.language())
    raise ValueError(f"Unsupported language: {name!r}")
