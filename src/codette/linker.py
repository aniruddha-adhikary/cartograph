"""Linker plugin protocol."""
from __future__ import annotations

from typing import Protocol


class Linker(Protocol):
    name: str

    def run(self, graph) -> None:  # pragma: no cover - protocol
        ...
