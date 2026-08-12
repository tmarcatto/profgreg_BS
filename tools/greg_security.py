from __future__ import annotations

from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WRITE_ROOTS = ("runs", "workspace", "tmp")


def resolve_under_root(value: str | Path, *, root: Path = ROOT) -> Path:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    root_resolved = root.resolve()
    if resolved == root_resolved or root_resolved in resolved.parents:
        return resolved
    raise ValueError(f"Path escapes Prof Greg workspace: {value}")


def safe_relative_path(value: str | Path) -> bool:
    text = str(value)
    path = Path(text)
    return bool(text.strip()) and not path.is_absolute() and ".." not in path.parts and not text.startswith(("~", "file://"))


def assert_safe_write_path(value: str | Path, *, allowed_roots: Iterable[str] = DEFAULT_WRITE_ROOTS, root: Path = ROOT) -> Path:
    resolved = resolve_under_root(value, root=root)
    relative = resolved.relative_to(root.resolve())
    first = relative.parts[0] if relative.parts else ""
    allowed = set(allowed_roots)
    if first not in allowed:
        raise ValueError(f"Write path must stay under one of {sorted(allowed)}: {value}")
    return resolved


def assert_safe_run_slug(value: str) -> str:
    if not value or "/" in value or "\\" in value or value in {".", ".."} or ".." in value:
        raise ValueError(f"Unsafe course/run slug: {value}")
    return value
