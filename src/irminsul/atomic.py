"""The one way a file is replaced: whole, or not at all."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def write_atomic(path: Path, text: str, *, newline: str | None = None) -> None:
    """Replace `path` with `text`, so a reader sees the old file or the new one, never half.

    The folder is created when it is missing. `text` carries LF endings. Unless `newline`
    pins them, the file is written back with the endings most of its lines had, so a CRLF
    working copy stays CRLF and a person's editor sees no churn; a file that does not exist
    yet gets LF. A generated file passes `newline="\\n"`, which fixes its bytes whatever the
    file held before.

    The text goes to a uniquely named file beside the target and is moved over it, and a
    failure removes that file, so a failed write leaves neither a partial target nor a
    stray temporary one, and a file a person named `<target>.tmp` is never overwritten.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ending = newline if newline is not None else _line_ending(path)
    scratch = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        with open(scratch, "x", encoding="utf-8", newline=ending) as handle:
            handle.write(text)
        os.replace(scratch, path)
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise


def _line_ending(path: Path) -> str:
    """The line ending most lines of the file at `path` use; LF for a file not there yet."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return "\n"
    return "\r\n" if raw.count(b"\r\n") * 2 > raw.count(b"\n") else "\n"
