"""Shared atomic text artifact persistence."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_replace_text(
    path: Path,
    content: str,
    *,
    temp_prefix: str | None = None,
) -> None:
    """Write UTF-8 text durably, then atomically replace its destination."""
    path = Path(path)
    parent = path.parent.absolute()
    target = parent / path.name
    parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{path.name}." if temp_prefix is None else temp_prefix
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=prefix,
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            stream = os.fdopen(descriptor, "w", encoding="utf-8")
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(descriptor)
            descriptor = None
            raise
        descriptor = None
        with stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        if (
            temporary is not None
            and temporary.parent == parent
            and temporary.name.startswith(prefix)
            and temporary.name.endswith(".tmp")
        ):
            with contextlib.suppress(OSError):
                temporary.unlink()
