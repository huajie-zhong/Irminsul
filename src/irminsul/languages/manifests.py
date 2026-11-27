"""What a language's manifests and directories say about where its code lives: a Go module's
path, a Rust package's name, the files beside an import's target.

A reader asks these to place an import, and keeps each answer in the run's memo, so one run
reads a manifest or lists a directory once and the next run reads the repository again.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from irminsul.languages.reader import SOURCE_FILES, Memo

_GO_MODULE_RE = re.compile(r"^\s*module\s+(\S+)", re.MULTILINE)
_GO_REPLACE_RE = re.compile(r"^\s*(?:replace\s+)?(\S+)(?:\s+\S+)?\s*=>\s*(\.{1,2}/\S*|\.{1,2})\s*$")
_GO_USE_RE = re.compile(r"^\s*(?:use\s+)?(\.{1,2}/\S*|\.{1,2})\s*$")
_GO_COMMENT_RE = re.compile(r"//.*")


def read_toml(path: Path) -> dict[str, object]:
    """A TOML file's table; empty when it is missing or does not parse."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def listing(directory: Path, memo: Memo) -> frozenset[str]:
    """The names directly in `directory`; none when it is not one."""
    key = ("listing", os.fspath(directory))
    if key not in memo:
        try:
            memo[key] = frozenset(os.listdir(directory))
        except OSError:
            memo[key] = frozenset()
    found = memo[key]
    assert isinstance(found, frozenset)
    return found


def nearest(start: Path, name: str, memo: Memo) -> Path | None:
    """The closest directory at or above `start` that holds a file called `name`, looked
    for as far up as the filesystem goes. A run asks each directory on the way once."""
    asked: list[Path] = []
    found: Path | None = None
    for directory in (start, *start.parents):
        key = ("nearest", os.fspath(directory), name)
        if key in memo:
            held = memo[key]
            assert held is None or isinstance(held, Path)
            found = held
            break
        asked.append(directory)
        if (directory / name).is_file():
            found = directory
            break
    for directory in asked:
        memo[("nearest", os.fspath(directory), name)] = found
    return found


def _unquoted(word: str) -> str:
    return word.strip('"`')


def _go_lines(path: Path, directive: str) -> list[str]:
    """The lines of one directive of a `go.mod` or `go.work` file, written alone or in a
    parenthesised block, comments left out."""
    out: list[str] = []
    in_block = False
    for raw in _text(path).splitlines():
        line = _GO_COMMENT_RE.sub("", raw).strip()
        if in_block:
            if line == ")":
                in_block = False
            elif line:
                out.append(line)
        elif line == f"{directive} (" or line == f"{directive}(":
            in_block = True
        elif line.startswith(f"{directive} "):
            out.append(line)
    return out


def _go_module_path(directory: Path) -> str | None:
    found = _GO_MODULE_RE.search(_text(directory / "go.mod"))
    return _unquoted(found.group(1)) if found else None


def source_files(memo: Memo) -> Sequence[Path]:
    """The files the run's walk of its source roots found; none where no run offers them."""
    listed = memo.get(SOURCE_FILES)
    return listed() if callable(listed) else ()


def _go_declared(roots: Sequence[Path], memo: Memo) -> dict[str, tuple[Path, ...]]:
    """Each module the repository's Go code is in, by its path, with each directory whose
    `go.mod` declares it: the nearest `go.mod` above each Go file among the run's source
    files, and above each source root. A module another module only requires is found
    here: its code is in the repository, whichever copy of it a build would fetch."""
    key = ("go.declared", *map(os.fspath, roots))
    if key not in memo:
        holding = {path.parent for path in source_files(memo) if path.suffix == ".go"}
        homes = {
            home
            for directory in (*holding, *roots)
            if (home := nearest(directory, "go.mod", memo)) is not None
        }
        declared: dict[str, list[Path]] = {}
        for home in sorted(homes, key=lambda directory: directory.as_posix()):
            path = _go_module_path(home)
            if path is not None:
                declared.setdefault(path, []).append(home)
        memo[key] = {path: tuple(found) for path, found in declared.items()}
    held = memo[key]
    assert isinstance(held, dict)
    return held


def go_modules(
    importer: Path, roots: Sequence[Path], memo: Memo
) -> tuple[tuple[str, tuple[Path, ...]], ...]:
    """Each module path a Go file can import from its repository, with the directories that
    may hold it, the longest path first. The file's own build says where three kinds are:
    the module of the nearest `go.mod`, the modules it replaces with a local directory, and
    those a `go.work` above it uses. Any other module the repository declares is in each
    directory that declares it, since nothing says which of two copies the file means."""
    home = nearest(importer.parent, "go.mod", memo)
    key = ("go.modules", None if home is None else os.fspath(home), *map(os.fspath, roots))
    if key not in memo:
        modules: dict[str, tuple[Path, ...]] = {}
        if home is not None:
            own = _go_module_path(home)
            if own is not None:
                modules[own] = (home,)
            for line in _go_lines(home / "go.mod", "replace"):
                replaced = _GO_REPLACE_RE.match(line)
                if replaced is not None:
                    local = Path(os.path.normpath(home / replaced.group(2)))
                    modules.setdefault(_unquoted(replaced.group(1)), (local,))
            workspace = nearest(home, "go.work", memo)
            for line in _go_lines(workspace / "go.work", "use") if workspace is not None else ():
                used = _GO_USE_RE.match(line)
                if used is not None and workspace is not None:
                    directory = Path(os.path.normpath(workspace / used.group(1)))
                    path = _go_module_path(directory)
                    if path is not None:
                        modules.setdefault(path, (directory,))
        for path, directories in _go_declared(roots, memo).items():
            modules.setdefault(path, directories)
        memo[key] = tuple(sorted(modules.items(), key=lambda item: -len(item[0])))
    held = memo[key]
    assert isinstance(held, tuple)
    return held


def cargo_package(importer: Path, memo: Memo) -> tuple[Path, frozenset[str]] | None:
    """The directory of the Rust package that holds `importer`, by the nearest `Cargo.toml`,
    and the names its library is imported under: the package's, hyphens as underscores,
    and the one a `[lib]` table gives it. None outside any package."""
    home = nearest(importer.parent, "Cargo.toml", memo)
    if home is None:
        return None
    key = ("cargo.package", os.fspath(home))
    if key not in memo:
        manifest = read_toml(home / "Cargo.toml")
        names = [
            table.get("name")
            for table in (manifest.get("package"), manifest.get("lib"))
            if isinstance(table, dict)
        ]
        memo[key] = frozenset(n.replace("-", "_") for n in names if isinstance(n, str))
    held = memo[key]
    assert isinstance(held, frozenset)
    return home, held
