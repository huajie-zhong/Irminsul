"""Go's reader: the shared tree-sitter reader with Go's grammar, and what a query cannot
say: what an import binds, and which files an import path names.

An import path names a package, which is a directory. It is placed through the module paths
its repository declares: the nearest `go.mod`, the local directories that file's `replace`
lines name, the modules a `go.work` above it uses, and every other module that holds a Go
file among the run's source files, by the `go.mod` nearest above it. Every other path is
the standard library's or another repository's, so under a `go.mod` this reader places
every import. A file with none above it has no module, and nothing says where its import
paths lead.

A file also reads every name of the other files of its package, with no import statement,
so its `package` clause is read as an import of them: a test beside the code it tests is
found as importing it, and two files of one package that different docs own are related.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import tree_sitter_go
from tree_sitter import Node

from irminsul.languages.manifests import go_modules, listing, nearest
from irminsul.languages.reader import ImportedName, Memo
from irminsul.languages.tree_sitter_reader import TreeSitterReader, node_text, query_file

_VERSION_RE = re.compile(r"v\d+")
_PACKAGE_RE = re.compile(r"^\s*package\s+(\w+)", re.MULTILINE)
#: What a file's `package` clause is read as importing: its own directory.
OWN_PACKAGE = "."
_EVERY_NAME = ImportedName("*", "*", "*", None)


def _package_name(path: str) -> str:
    """The name a package is used under when its import gives none: the last element of
    its path, a major version aside, as in `example.com/lib/v2` and `gopkg.in/yaml.v3`."""
    parts = [part for part in path.split("/") if part]
    if len(parts) > 1 and _VERSION_RE.fullmatch(parts[-1]):
        parts.pop()
    return re.sub(r"\.v\d+$", "", parts[-1]) if parts else path


def imports_of(node: Node) -> Sequence[tuple[str, tuple[ImportedName, ...]]]:
    """One import spec as its path and the package name it binds: its alias, every name of
    the package for `.`, nothing for `_`, and else the package's own name. A `package`
    clause is every name of the file's own package."""
    if node.type == "package_clause":
        return ((OWN_PACKAGE, (_EVERY_NAME,)),)
    path = node.child_by_field_name("path")
    if path is None:
        return ()
    source = node_text(path).strip('"`')
    alias = node.child_by_field_name("name")
    if alias is None:
        local = _package_name(source)
    elif alias.type == "dot":
        return ((source, (_EVERY_NAME,)),)
    elif alias.type == "blank_identifier":
        return ((source, ()),)
    else:
        local = node_text(alias)
    return ((source, (ImportedName(local, None, local, None),)),)


def _package_files(package: Path, memo: Memo) -> list[Path]:
    """The Go files of the package in the directory `package`, its tests aside."""
    return [
        package / name
        for name in sorted(listing(package, memo))
        if name.endswith(".go") and not name.endswith("_test.go")
    ]


def files_of(source: str, importer: Path, roots: Sequence[Path], memo: Memo) -> list[Path]:
    """The Go files of the package `source` names, its tests aside, when a module of the
    importer's repository holds it: the importer's own package without the importer, and
    none for a package of the standard library or of another repository. A module two
    directories declare is in both, so the package is looked for in each."""
    if source == OWN_PACKAGE:
        return [path for path in _package_files(importer.parent, memo) if path != importer]
    for module, directories in go_modules(importer, roots, memo):
        if source == module or source.startswith(f"{module}/"):
            inside = source[len(module) :].split("/")
            return [
                path
                for directory in directories
                for path in _package_files(directory.joinpath(*inside), memo)
            ]
    return []


def mentioned_as(path: Path) -> frozenset[str] | None:
    """A file that imports the package of `path` spells the last element of the package's
    import path, and a file of the same package spells the package's name, which the file
    itself gives. None outside any module, where nothing says what the import path is."""
    package = path.parent
    try:
        own = _PACKAGE_RE.search(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        own = None
    for module, directories in go_modules(path, (), {}):
        for directory in directories:
            if package == directory or directory in package.parents:
                inside = package.relative_to(directory).as_posix()
                imported = f"{module}/{inside}".rstrip("/.").rsplit("/", 1)[-1]
                return frozenset({imported, *([own.group(1)] if own else [])})
    return None


def places_imports(path: Path, memo: Memo) -> bool:
    """Whether a `go.mod` stands above the file `path`: only then does its module say where
    each of its import paths leads."""
    return nearest(path.parent, "go.mod", memo) is not None


GO_READER = TreeSitterReader(
    tree_sitter_go.language,
    query_file("go"),
    imports_of=imports_of,
    files_of=files_of,
    mentioned_as=mentioned_as,
    places_imports=places_imports,
)
