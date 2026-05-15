from __future__ import annotations

from pathlib import Path


def layer_dirs(workspace: Path | None = None, explicit: list[Path] | None = None) -> list[Path]:
    dirs: list[Path] = []
    if workspace:
        project = workspace / ".cartograph"
        if project.exists():
            dirs.append(project)
    dirs.extend(explicit or [])
    return dirs


def pack_dirs(layers: list[Path]) -> list[Path]:
    return [layer / "packs" for layer in layers if (layer / "packs").exists()]


def view_dirs(layers: list[Path]) -> list[Path]:
    return [layer / "views" for layer in layers if (layer / "views").exists()]


def lens_dirs(layers: list[Path]) -> list[Path]:
    return [layer / "lenses" for layer in layers if (layer / "lenses").exists()]
