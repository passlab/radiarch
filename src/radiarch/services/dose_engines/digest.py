"""The digest of an engine's build: its program and the data files a run reads (roadmap R12).

A result keeps the digest of the build that computed it, so that an approval can name that exact build, and a build
that changed under the same version number shows as a different one. The digest is SHA-256 over each file's name and
bytes, in name order; it is cached per process by path, inode, size and modification and change times.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from loguru import logger

_Entry = Tuple[str, str, int, int, int, int]          # name, resolved path, inode, size, mtime_ns, ctime_ns


@lru_cache(maxsize=64)
def _digest(entries: Tuple[_Entry, ...]) -> str:
    h = hashlib.sha256()
    for name, path, *_ in entries:
        h.update(name.encode("utf-8") + b"\0")
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def bytes_digest(items: Iterable[Tuple[str, bytes]]) -> str:
    """As ``files_digest``, over (name, bytes) already read: what a run loaded rather than what is on disk now."""
    h = hashlib.sha256()
    for name, data in sorted(items, key=lambda item: item[0]):
        h.update(name.encode("utf-8") + b"\0" + data + b"\0")
    return h.hexdigest()


def files_digest(files: Iterable[Path], root: Optional[Path] = None) -> str:
    """SHA-256 over the files, each named by its path under ``root`` (or its file name, for a file outside it)."""
    entries = {}
    for p in files:
        p = Path(p).resolve()
        st = p.stat()
        try:
            name = p.relative_to(Path(root).resolve()).as_posix() if root is not None else p.name
        except ValueError:
            name = p.name
        entries[str(p)] = (name, str(p), st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)      # one entry per file
    return _digest(tuple(sorted(entries.values())))


def tree_files(directory: Path) -> List[Path]:
    """Every regular file under ``directory``."""
    return sorted(p for p in Path(directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def common_digest(digests: Iterable[Optional[str]]) -> Optional[str]:
    """The one digest that every input shares; None when they differ or one is unknown. A result computed from cached
    matrices names the build that made them, not the build running now."""
    found = set(digests)
    return found.pop() if len(found) == 1 else None


def engine_digest(name: Optional[str], params: Optional[dict] = None) -> Optional[str]:
    """The digest of the registered engine ``name`` for a run with ``params`` (``pb+arcs`` reads as ``pb``); None for
    an engine without build files, or when they cannot be read. A digest never fails a computation."""
    base = (name or "").split("+")[0]
    if not base:
        return None
    try:
        from .registry import get_engine

        digest = getattr(get_engine(base), "digest", None)
        return digest(params) if digest is not None else None
    except Exception as exc:
        logger.warning("engine {}: no digest ({})", base, exc)
        return None


__all__ = ["bytes_digest", "common_digest", "engine_digest", "files_digest", "tree_files"]
