"""Whether a code span names a file, and whether the repository holds a file by that name."""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from irminsul.docgraph import DocGraph
from irminsul.languages import LANGUAGE_REGISTRY

_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]+")
_CONFIG_SUFFIXES = frozenset({".md", ".toml", ".yml", ".yaml", ".json"})


def _skipped(directory: Path) -> bool:
    """Whether the file index leaves `directory` out: git's own, one a language's tools write
    to or install other projects' code in, or an installed environment, each as a profile
    lists it."""
    name = directory.name
    return name == ".git" or any(
        name in profile.cache_dirs
        or name in profile.dependency_dirs
        or any((directory / marker).exists() for marker in profile.environment_markers)
        for profile in LANGUAGE_REGISTRY.values()
    )


def path_suffixes(enabled_languages: Iterable[str]) -> frozenset[str]:
    """The extensions that make a bare name, one without a `/`, read as a file path."""
    return _CONFIG_SUFFIXES | {
        suffix
        for name in enabled_languages
        if name in LANGUAGE_REGISTRY
        for suffix in LANGUAGE_REGISTRY[name].suffixes
    }


def named_path(span: str, suffixes: frozenset[str]) -> str | None:
    """The file path `span` is written as, or None when it is not written like one.

    A path has no whitespace, glob or URL scheme, and either a `/` before a last segment that
    ends in an extension of letters and digits, or is a bare name ending in one of `suffixes`.
    A string literal's quotes, as a config table writes a default value, are not part of it.
    """
    text = span.strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if not text or any(c.isspace() for c in text) or "*" in text or "://" in text:
        return None
    suffix = PurePosixPath(text.rsplit("/", 1)[-1]).suffix
    if not _EXTENSION_RE.fullmatch(suffix):
        return None
    return text if "/" in text or suffix in suffixes else None


class FileIndex:
    """The files a repository holds, under every spelling a doc may use for one.

    A file counts under its repo-relative path and under each tail of it, so `links.py` and
    `checks/links.py` both name `src/irminsul/checks/links.py`. Files git lists, tracked or
    not yet ignored, and the source files of a root outside the repository come first; a
    file only the disk holds, such as a generated one, is looked for when those miss.
    """

    def __init__(self, graph: DocGraph) -> None:
        assert graph.repo_root is not None
        self._root = graph.repo_root
        self._files: set[str] = set()
        self._tails: set[str] = set()
        self._walked = False
        listing = graph.git.text_live(
            self._root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
        )
        if listing is None:
            self._walk()
        else:
            for display in listing.split("\0"):
                self._add(display)
        for _, display in graph.source.files:
            self._add(display)
        for display in graph.source.test_displays:
            self._add(display)

    def holds(self, span: str, doc_dir: str) -> bool:
        """Whether a file is named by `span`, written in a doc in `doc_dir` (repo-relative)."""
        if span in self._tails:
            return True
        beside = posixpath.normpath(posixpath.join(doc_dir, span))
        if beside in self._files or (self._root / beside).is_file():
            return True
        if (self._root / span).is_file():
            return True
        if not self._walked:
            self._walk()
        return span in self._tails

    def _add(self, display: str) -> None:
        if not display:
            return
        self._files.add(display)
        parts = display.split("/")
        self._tails.update("/".join(parts[i:]) for i in range(len(parts)))

    def _walk(self) -> None:
        """Every file under the repository root outside `.git`, dependency and virtual-env
        directories, which is how a generated file git ignores is found."""
        self._walked = True
        for directory, names, files in os.walk(self._root):
            names[:] = [n for n in names if not _skipped(Path(directory) / n)]
            base = Path(directory).relative_to(self._root).as_posix()
            for name in files:
                self._add(name if base == "." else f"{base}/{name}")
