from __future__ import annotations

from pathlib import Path


def media_stem(path: Path) -> str:
    """Return the original media stem from a media or generated subtitle path."""
    stem = Path(path).expanduser().stem
    for suffix in (".zh-Hans", ".zh-Hant", ".en"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def output_directory(source: Path, root: Path | None = None) -> Path:
    """Place artifacts in a folder named after the original media."""
    source = Path(source).expanduser().resolve()
    media_name = media_stem(source)
    base = Path(root).expanduser().resolve() if root else source.parent
    directory = base if base.name == media_name else base / media_name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def organized_output_path(source: Path, requested: Path | None, default_name: str) -> Path:
    requested = Path(requested).expanduser() if requested else None
    root = requested.parent if requested else None
    directory = output_directory(source, root)
    return directory / (requested.name if requested else default_name)
