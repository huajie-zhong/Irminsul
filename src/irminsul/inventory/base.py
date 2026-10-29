"""Static surface extractors.

Each extractor turns source files into a list of `SurfaceItem` identities for one
*kind* of code surface (CLI commands, HTTP endpoints, exports, env vars). They are
**static only** — irminsul must never import or execute a target repo's code, so
extraction is AST/regex over file text, never `import`.

Adding a kind = add an extractor or rule to a pack in `packs.py`; nothing in the checks
needs to change.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

from irminsul.languages.python import PYTHON_PROFILE


@dataclass(frozen=True)
class SurfaceItem:
    """One extracted surface element.

    `identity` is the diff key (e.g. ``"list review"``, ``"GET /api/check"``,
    a symbol name, or an env-var name). `display`/`line` are best-effort provenance
    for human-facing output and are never compared.
    """

    identity: str
    display: str | None = None
    line: int | None = None


@runtime_checkable
class Extractor(Protocol):
    @property
    def kind(self) -> str: ...

    def extract(
        self, source_files: list[tuple[Path, str]], reader: SourceReader
    ) -> list[SurfaceItem]: ...


def dedupe(items: list[SurfaceItem]) -> list[SurfaceItem]:
    """Keep the first occurrence of each identity, preserving order."""
    seen: set[str] = set()
    out: list[SurfaceItem] = []
    for item in items:
        if item.identity in seen:
            continue
        seen.add(item.identity)
        out.append(item)
    return out


@dataclass(frozen=True)
class PythonModule:
    """A Python file's syntax tree, and every node in it in `ast.walk` order."""

    tree: ast.Module

    @cached_property
    def nodes(self) -> tuple[ast.AST, ...]:
        return tuple(ast.walk(self.tree))

    @classmethod
    def parse(cls, text: str) -> PythonModule | None:
        """The module `text` holds, or None when it does not parse."""
        try:
            return cls(ast.parse(text))
        except SyntaxError:
            return None


class SourceReader:
    """Files read and parsed at most once each, for the life of the reader.

    A file that is missing, unreadable or not UTF-8 carries no surface the extractors can
    see, and one such file in a source root must not stop a run over the rest, so it
    reads as None; so does Python that does not parse. Keyed by the path's spelling rather
    than by `Path`, which compares case-insensitively on Windows even where the filesystem
    does not.
    """

    def __init__(self) -> None:
        self._texts: dict[str, str | None] = {}
        self._modules: dict[str, PythonModule | None] = {}

    def text(self, path: Path) -> str | None:
        key = os.fspath(path)
        if key not in self._texts:
            try:
                self._texts[key] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                self._texts[key] = None
        return self._texts[key]

    def module(self, path: Path) -> PythonModule | None:
        key = os.fspath(path)
        if key not in self._modules:
            text = self.text(path)
            self._modules[key] = None if text is None else PythonModule.parse(text)
        return self._modules[key]

    def python_modules(
        self, source_files: Iterable[tuple[Path, str]]
    ) -> Iterator[tuple[PythonModule, str]]:
        """Each Python file of `source_files` that parses, with its display path."""
        for abs_path, display in source_files:
            if PurePosixPath(display).suffix not in PYTHON_PROFILE.suffixes:
                continue
            module = self.module(abs_path)
            if module is not None:
                yield module, display
