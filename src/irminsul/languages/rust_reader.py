"""Rust's reader: the shared tree-sitter reader with Rust's grammar, and what a query cannot
say: the paths a `use` tree names, and which files a path may be.

A path is placed inside its own package: from `crate`, `self`, `super`, or the package's own
name as its tests and binaries spell it, to the `.rs` file or the `mod.rs` of a module. A
path into another crate, a workspace member included, is not followed, so this reader does
not place every import.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import tree_sitter_rust
from tree_sitter import Node

from irminsul.languages.manifests import cargo_package
from irminsul.languages.reader import ImportedName, Memo
from irminsul.languages.tree_sitter_reader import TreeSitterReader, node_text, query_file

#: The files that are a crate's or a directory's own module, not a child of it.
_ROOTS = frozenset({"lib.rs", "main.rs", "mod.rs"})


def _segments(node: Node) -> list[str]:
    """A path such as `crate::loans::policy` as its segments."""
    if node.type in ("scoped_identifier", "scoped_type_identifier"):
        path, name = node.child_by_field_name("path"), node.child_by_field_name("name")
        return [
            *(_segments(path) if path is not None else []),
            *([node_text(name)] if name else []),
        ]
    return [node_text(node)]


def _leaves(node: Node, prefix: list[str]) -> list[tuple[list[str], str | None, str | None]]:
    """Each name a `use` tree binds, as the module path before it, the name there, and the
    name it is bound under: (`[a, b]`, `c`, `d`) for `a::b::c as d`. The name is `*` for a
    glob and None for `self`, which binds the module itself."""
    if node.type == "scoped_use_list":
        path, items = node.child_by_field_name("path"), node.child_by_field_name("list")
        inner = [*prefix, *(_segments(path) if path is not None else [])]
        return _leaves(items, inner) if items is not None else []
    if node.type == "use_list":
        return [leaf for child in node.named_children for leaf in _leaves(child, prefix)]
    if node.type == "use_wildcard":
        path = next(iter(node.named_children), None)
        return [([*prefix, *(_segments(path) if path is not None else [])], "*", "*")]
    if node.type == "use_as_clause":
        path, alias = node.child_by_field_name("path"), node.child_by_field_name("alias")
        if path is None or alias is None:
            return []
        parts = [*prefix, *_segments(path)]
        return [(parts[:-1], parts[-1], node_text(alias))]
    parts = [*prefix, *_segments(node)]
    if parts and parts[-1] == "self":
        return [(parts[:-1], None, parts[-2])] if len(parts) > 1 else []
    return [(parts[:-1], parts[-1], parts[-1])] if parts else []


def _inline_depth(node: Node) -> int:
    """How many modules with a body, written in this file, hold `node`."""
    depth = 0
    ancestor = node.parent
    while ancestor is not None:
        depth += ancestor.type == "mod_item"
        ancestor = ancestor.parent
    return depth


def _from_the_file(module: list[str], depth: int) -> list[str]:
    """A module path written `depth` inline modules deep, as the file's top level would
    write it: each `super` up to that depth stays inside the file, so `super` in
    `mod tests` is `self`."""
    if depth == 0 or not module or module[0] not in ("self", "super"):
        return module
    rest = module[1:] if module[0] == "self" else module
    climbed = 0
    while climbed < depth and rest and rest[0] == "super":
        rest, climbed = rest[1:], climbed + 1
    return rest if rest and rest[0] == "super" else ["self", *rest]


def imports_of(node: Node) -> Sequence[tuple[str, tuple[ImportedName, ...]]]:
    """One `use` declaration as the modules it names and what it binds of each."""
    argument = node.child_by_field_name("argument")
    if argument is None:
        return ()
    depth = _inline_depth(node)
    by_module: dict[str, list[ImportedName]] = {}
    for module, name, local in _leaves(argument, []):
        if local is None:
            continue
        if not module:
            # `use policy;` binds the crate or module `policy` itself.
            by_module.setdefault(local if name is None else name, []).append(
                ImportedName(local, None, local, None)
            )
            continue
        source = "::".join(_from_the_file(module, depth))
        if name is None:
            bound = ImportedName(local, None, local, None)
        elif name == "*":
            bound = ImportedName("*", "*", "*", None)
        else:
            bound = ImportedName(local, name, local, f"{source}::{name}")
        by_module.setdefault(source, []).append(bound)
    return tuple((source, tuple(names)) for source, names in by_module.items())


def _own_module(importer: Path, package: Path) -> tuple[Path, list[str]]:
    """The directory a crate's module paths start in, and the path of the module the file
    `importer` is. A file under the package's `src` belongs to the crate rooted there,
    but for `src/bin`, where each file or directory is a binary crate of its own, as a
    test, an example and a build script outside `src` each are."""
    source = package / "src"
    if source not in importer.parents:
        return importer.parent, []
    inside = list(importer.relative_to(source).parts)
    if inside[0] == "bin" and len(inside) > 1:
        if len(inside) == 2:
            return importer.parent, []
        source, inside = source / "bin" / inside[1], inside[2:]
    return source, inside[:-1] if inside[-1] in _ROOTS else [*inside[:-1], importer.stem]


def files_of(source: str, importer: Path, roots: Sequence[Path], memo: Memo) -> list[Path]:
    """The files the module path `source` may be, inside the importer's own package: the
    module's `.rs` file and its `mod.rs`, or the crate's root for the crate itself."""
    found = cargo_package(importer, memo)
    if found is None:
        return []
    package, names = found
    parts = source.split("::")
    base, own = _own_module(importer, package)
    if parts[0] == "crate":
        module = parts[1:]
    elif parts[0] in names:
        base, module = package / "src", parts[1:]
    elif parts[0] == "self":
        module = [*own, *parts[1:]]
    elif parts[0] == "super":
        module, rest = list(own), parts
        while rest and rest[0] == "super":
            if not module:
                return []
            module, rest = module[:-1], rest[1:]
        module = [*module, *rest]
    else:
        return []
    if not module:
        return [base / "lib.rs", base / "main.rs"]
    target = base.joinpath(*module)
    return [target.with_name(f"{target.name}.rs"), target / "mod.rs"]


def mentioned_as(path: Path) -> frozenset[str] | None:
    """A file that imports the module of `path` spells the module's name: the file's stem,
    or its directory's for `mod.rs`; a crate's root is imported as `crate` or by the
    package's name, which the path does not hold."""
    if path.name in ("lib.rs", "main.rs"):
        return None
    name = path.parent.name if path.name == "mod.rs" else path.stem
    return frozenset({name}) if name else None


RUST_READER = TreeSitterReader(
    tree_sitter_rust.language,
    query_file("rust"),
    imports_of=imports_of,
    files_of=files_of,
    mentioned_as=mentioned_as,
)
