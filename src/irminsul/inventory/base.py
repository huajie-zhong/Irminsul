"""Static surface extractors.

Each extractor turns source files into a list of `SurfaceItem` identities for one
*kind* of code surface (CLI commands, HTTP endpoints, exports, env vars). They are
**static only** — irminsul must never import or execute a target repo's code, so
extraction is AST/regex over file text, never `import`.

Adding a kind = add an extractor or rule to a pack in `packs.py`; nothing in the checks
needs to change.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

from irminsul.languages import reader_for
from irminsul.languages.python import PYTHON_PROFILE
from irminsul.languages.python_reader import PYTHON_READER, PythonReading
from irminsul.languages.python_reader import PythonModule as PythonModule
from irminsul.languages.reader import SOURCE_FILES, CodeReader, CodeReading, Memo


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


class SourceReader:
    """Files read and parsed at most once each, for the life of the reader.

    A file that is missing, unreadable or not UTF-8 carries no surface the extractors can
    see, and one such file in a source root must not stop a run over the rest, so it
    reads as None; so does Python that does not parse, as a module, while its reading says
    it did not parse. Keyed by the path's spelling rather than by `Path`, which compares
    case-insensitively on Windows even where the filesystem does not.
    """

    def __init__(self, files: Callable[[], Sequence[Path]] | None = None) -> None:
        """`files` gives the files of the repository's source roots, when the one who
        builds this reader has walked them: it is offered to each language's reader and
        called only if one asks, so reading one file walks nothing."""
        self._listed = files
        self._texts: dict[str, str | None] = {}
        self._readings: dict[tuple[str, CodeReader], CodeReading | None] = {}
        self._memos: dict[CodeReader, Memo] = {}

    def text(self, path: Path) -> str | None:
        key = os.fspath(path)
        if key not in self._texts:
            try:
                self._texts[key] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                self._texts[key] = None
        return self._texts[key]

    def reading(self, path: Path) -> CodeReading | None:
        """The file as its language's reader reads it; None when no language with a reader
        lists its suffix, or it cannot be read as text."""
        reader = reader_for(path)
        return None if reader is None else self.read_with(path, reader)

    def module(self, path: Path) -> PythonModule | None:
        """The file's Python syntax tree, which the framework extractors read, whatever its
        suffix; None when it does not parse. It is the parse Python's reader reads, so a file
        both read is parsed once."""
        reading = self.read_with(path, PYTHON_READER)
        return reading.module if isinstance(reading, PythonReading) else None

    def read_with(self, path: Path, reader: CodeReader) -> CodeReading | None:
        """The file as `reader` reads it, read once; None when it cannot be read as text."""
        key = (os.fspath(path), reader)
        if key not in self._readings:
            text = self.text(path)
            self._readings[key] = None if text is None else reader.read(text, self._memo(reader))
        return self._readings[key]

    def read_text(self, path: Path, text: str) -> CodeReading | None:
        """`text` as the reader of the file `path` reads it, with what this run knows of
        the repository: for a revision of the file, which the disk does not hold, so it is
        not kept. None when no reader reads the file."""
        reader = reader_for(path)
        return None if reader is None else reader.read(text, self._memo(reader))

    def _memo(self, reader: CodeReader) -> Memo:
        """What `reader` keeps for the life of this reader of sources, with the listing of
        the source files on offer when there is one."""
        if reader not in self._memos:
            memo: Memo = {}
            if self._listed is not None:
                memo[SOURCE_FILES] = self._listed
            self._memos[reader] = memo
        return self._memos[reader]

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
