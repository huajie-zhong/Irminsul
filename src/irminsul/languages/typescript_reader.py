"""TypeScript's and JavaScript's readers: the shared tree-sitter reader with the TypeScript
grammar, its TSX dialect for `.tsx` and for every JavaScript suffix, and what a query cannot
say: how an import's names bind, and which files a specifier may load.

A specifier is placed where the language says so plainly: a relative one, against the
importing file's directory. A bare one names a package, a path alias or a file under a
configured base, and which of them is not in the file, so it is not followed, and this
reader does not place every import.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

import tree_sitter_typescript
from tree_sitter import Node

from irminsul.languages.manifests import listing
from irminsul.languages.reader import ImportedName, Memo
from irminsul.languages.tree_sitter_reader import TreeSitterReader, node_text, query_file
from irminsul.languages.typescript import TYPESCRIPT_PROFILE

#: The suffixes a specifier may leave out, a declaration file's included.
_RESOLVED = (*TYPESCRIPT_PROFILE.suffixes, ".d.ts")
#: A TypeScript file is imported under the JavaScript suffix it compiles to.
_COMPILED = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}


def _module(local: str) -> ImportedName:
    return ImportedName(local, None, local, None)


def _named(local: str, name: str) -> ImportedName:
    return ImportedName(local, name, local, None)


def _clause_names(clause: Node) -> list[ImportedName]:
    """What an `import` clause binds: a default import, a namespace, and named imports."""
    out: list[ImportedName] = []
    for child in clause.named_children:
        if child.type == "identifier":
            out.append(_named(node_text(child), "default"))
        elif child.type == "namespace_import":
            out.extend(_module(node_text(n)) for n in child.named_children)
        elif child.type == "named_imports":
            for specifier in child.named_children:
                name = specifier.child_by_field_name("name")
                alias = specifier.child_by_field_name("alias")
                if name is not None:
                    out.append(_named(node_text(alias or name), node_text(name).strip("\"'")))
    return out


def _required_names(call: Node) -> list[ImportedName]:
    """What `const x = require(...)` or `const { a, b: c } = require(...)` binds."""
    declarator = call.parent
    if declarator is None or declarator.type != "variable_declarator":
        return []
    target = declarator.child_by_field_name("name")
    if target is None:
        return []
    if target.type == "identifier":
        return [_module(node_text(target))]
    out: list[ImportedName] = []
    for part in target.named_children if target.type == "object_pattern" else ():
        if part.type == "shorthand_property_identifier_pattern":
            out.append(_named(node_text(part), node_text(part)))
        elif part.type == "pair_pattern":
            key, value = part.child_by_field_name("key"), part.child_by_field_name("value")
            if key is not None and value is not None and value.type == "identifier":
                out.append(_named(node_text(value), node_text(key)))
    return out


def _source(node: Node) -> str | None:
    """The specifier of an import node: the one string it names."""
    holder = node.child_by_field_name("source")
    if holder is None and node.type == "import_statement":
        clause = next((c for c in node.named_children if c.type == "import_require_clause"), None)
        holder = clause.child_by_field_name("source") if clause is not None else None
    if holder is None and node.type == "call_expression":
        arguments = node.child_by_field_name("arguments")
        holder = arguments.named_children[0] if arguments and arguments.named_children else None
    if holder is None or holder.type != "string":
        return None
    return "".join(node_text(part) for part in holder.named_children)


def imports_of(node: Node) -> Sequence[tuple[str, tuple[ImportedName, ...]]]:
    """One import as its specifier and the names it binds: `import` in each of its forms, a
    re-export, which binds nothing, `require` and `import()` of a string."""
    source = _source(node)
    if source is None:
        return ()
    names: list[ImportedName] = []
    if node.type == "import_statement":
        for child in node.named_children:
            if child.type == "import_clause":
                names.extend(_clause_names(child))
            elif child.type == "import_require_clause":
                names.extend(
                    _module(node_text(n)) for n in child.named_children if n.type == "identifier"
                )
    elif node.type == "call_expression":
        names.extend(_required_names(node))
    return ((source, tuple(names)),)


def _candidates(target: Path, memo: Memo) -> list[Path]:
    """The files that `target`, a specifier joined to a directory, may be: itself, itself
    under a suffix it left out or was compiled from, or the index file of its directory."""
    beside = listing(target.parent, memo)
    names = [target.name] if target.suffix in _RESOLVED else []
    stems = [target.name]
    for compiled in _COMPILED.get(target.suffix, ()):
        names.append(target.stem + compiled)
    names.extend(stem + suffix for stem in stems for suffix in _RESOLVED)
    out = [target.parent / name for name in dict.fromkeys(names) if name in beside]
    inside = listing(target, memo)
    out.extend(target / f"index{suffix}" for suffix in _RESOLVED if f"index{suffix}" in inside)
    return out


def files_of(source: str, importer: Path, roots: Sequence[Path], memo: Memo) -> list[Path]:
    """The files a relative specifier may load that exist, beside the importing file; none
    for any other specifier."""
    if not source.startswith("."):
        return []
    return _candidates(Path(os.path.normpath(importer.parent / source)), memo)


def mentioned_as(path: Path) -> frozenset[str] | None:
    """A file that imports `path` spells its stem, or its directory's name for an index
    file."""
    stem = path.name.split(".", 1)[0]
    name = path.parent.name if stem == "index" else stem
    return frozenset({name}) if name else None


def _queries(*languages: str) -> Callable[[], str]:
    files = [query_file(language) for language in languages]
    return lambda: "\n".join(read() for read in files)


TYPESCRIPT_READER = TreeSitterReader(
    tree_sitter_typescript.language_typescript,
    _queries("typescript"),
    imports_of=imports_of,
    files_of=files_of,
    mentioned_as=mentioned_as,
)
TSX_READER = TreeSitterReader(
    tree_sitter_typescript.language_tsx,
    _queries("typescript", "tsx"),
    imports_of=imports_of,
    files_of=files_of,
    mentioned_as=mentioned_as,
)
