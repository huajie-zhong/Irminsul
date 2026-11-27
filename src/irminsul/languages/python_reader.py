"""Python's reader: the language's own parser, `ast`, answering what a file defines and
imports, what a definition's body refers to, the text a pin hashes, and which functions are
tests.

The framework extractors in `irminsul.inventory` read the same parse, `PythonModule`, so a
file read for both is parsed once.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from irminsul.languages.reader import (
    Definition,
    DefinitionKind,
    Import,
    ImportedName,
    Memo,
    References,
)


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


_Function = ast.FunctionDef | ast.AsyncFunctionDef
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_Import = ast.Import | ast.ImportFrom
#: The nodes that bind the name they carry: a nested definition, an `except ... as` name,
#: and a `match` capture.
_Binder = _Function | ast.ClassDef | ast.ExceptHandler | ast.MatchAs | ast.MatchStar
_NOTHING = References(frozenset(), frozenset(), frozenset(), ())


def _target_names(target: ast.expr) -> Iterator[str]:
    """The plain names one assignment target binds, unpacking tuples and lists.

    An attribute or subscript target is deliberately not a definition: `cfg.limit = 5`
    mentions `cfg` without binding it, so anchoring `#cfg` to that line would pin a claim
    to a statement that does not define what it names.
    """
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Starred):
        yield from _target_names(target.value)
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _target_names(element)


def _bound_names(node: ast.stmt) -> list[str]:
    """The names an assignment statement binds, each once, in the order it writes them."""
    if isinstance(node, ast.AnnAssign):
        return list(dict.fromkeys(_target_names(node.target)))
    if isinstance(node, ast.Assign):
        return list(dict.fromkeys(n for target in node.targets for n in _target_names(target)))
    return []


def _defines(node: ast.stmt, name: str) -> bool:
    """Whether this statement is the definition of `name` in its own scope."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return node.name == name
    if isinstance(node, ast.AnnAssign):
        return name in _target_names(node.target)
    if isinstance(node, ast.Assign):
        return any(name in _target_names(target) for target in node.targets)
    return False


def _find_symbol(tree: ast.Module, symbol: str) -> ast.AST | None:
    """Resolve a name bound at the top level, or a dotted `Class.member`.

    A name is bound by a function, a class, or an assignment, so a threshold or a registry
    can be anchored as readily as a function. Only a class opens a scope to descend into:
    an assignment binds no members, so `LIMIT.attr` resolves to nothing rather than to the
    statement that binds `LIMIT`.
    """
    parts = symbol.split(".")
    scope: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for part in parts:
        node = next((child for child in scope if _defines(child, part)), None)
        if node is None:
            return None
        scope = node.body if isinstance(node, ast.ClassDef) else []
    return node


def _statement_bodies(node: ast.stmt) -> Iterator[list[ast.stmt]]:
    for field_name in ("body", "orelse", "finalbody"):
        value = getattr(node, field_name, None)
        if isinstance(value, list) and all(isinstance(item, ast.stmt) for item in value):
            yield value
    for handler in getattr(node, "handlers", []):
        yield handler.body
    for case in getattr(node, "cases", []):
        yield case.body


def _canonical(value: object) -> str:
    """A syntax tree, or a field of one, as text that depends on nothing but the tree: each
    node's type and fields, never its position, and no field that is None or empty, so a
    field a newer Python adds does not move the hash of code that leaves it unset.

    Not `ast.unparse`, whose printing of one tree changes between patch releases. A leaf is
    written with `ascii` rather than `repr`, which escapes a character or not by the
    interpreter's Unicode version."""
    if isinstance(value, list):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if not isinstance(value, ast.AST):
        return ascii(value)
    fields: list[str] = []
    for name, field in ast.iter_fields(value):
        if isinstance(value, ast.JoinedStr):
            # 3.12.3 parses `f"{x:{w}}"` with an empty literal closing the format spec,
            # which later releases do not; it prints nothing either way.
            field = [p for p in field if not (isinstance(p, ast.Constant) and p.value == "")]
        if field is not None and field != []:
            fields.append(f"{name}={_canonical(field)}")
    return f"{type(value).__name__}({','.join(fields)})"


def _dotted(node: ast.expr) -> str | None:
    """`a.b.c` for a chain of attributes that starts at a bare name, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def _submodule(source: str, name: str) -> str:
    """The module `name` would be inside the module `source`, spelled as `source` is."""
    return f"{source}{name}" if source.endswith(".") else f"{source}.{name}"


def _imports_of(node: ast.Import | ast.ImportFrom, scope: tuple[str, ...]) -> tuple[Import, ...]:
    """One import statement as the imports it makes: one per module a plain `import` names,
    and one for a `from` import."""
    if isinstance(node, ast.Import):
        return tuple(
            Import(
                node.lineno,
                alias.name,
                (
                    ImportedName(
                        alias.asname or alias.name.split(".", 1)[0],
                        None,
                        alias.asname or alias.name,
                        None,
                    ),
                ),
                scope,
            )
            for alias in node.names
        )
    source = "." * node.level + (node.module or "")
    names = tuple(
        ImportedName(
            alias.asname or alias.name,
            alias.name,
            alias.asname or alias.name,
            None if alias.name == "*" else _submodule(source, alias.name),
        )
        for alias in node.names
    )
    return (Import(node.lineno, source, names, scope),)


def _module_files(base: Path, parts: list[str]) -> list[Path]:
    """The two files that can hold the module `parts` names under `base`."""
    if not parts:
        return [base / "__init__.py"]
    target = base.joinpath(*parts)
    return [target.with_suffix(".py"), target / "__init__.py"]


class _Walk:
    """Every definition and import of one module, read in one pass over its statements."""

    def __init__(self, tree: ast.Module | None) -> None:
        self.definitions: list[Definition] = []
        self.nodes: dict[Definition, ast.stmt] = {}
        self.imports: list[Import] = []
        self.by_statement: dict[int, tuple[Import, ...]] = {}
        if tree is not None:
            self._body(tree.body, (), True, False)

    def _body(
        self, body: list[ast.stmt], scope: tuple[str, ...], reachable: bool, local: bool
    ) -> None:
        """Read `body`, held by the definitions `scope` names. `reachable` says whether a
        dotted path still reaches it, and `local` whether it runs inside a function, where an
        assignment binds a local variable rather than anything a doc would name."""
        for node in body:
            end = node.end_lineno or node.lineno
            if isinstance(node, _DEFINITIONS):
                first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
                kind: DefinitionKind = "type" if isinstance(node, ast.ClassDef) else "function"
                self._add(
                    Definition(node.name, kind, scope, node.lineno, first, end, reachable), node
                )
            elif not local:
                for name in _bound_names(node):
                    self._add(
                        Definition(
                            name, "variable", scope, node.lineno, node.lineno, end, reachable
                        ),
                        node,
                    )
            if isinstance(node, _Import):
                made = _imports_of(node, scope)
                self.by_statement[id(node)] = made
                self.imports.extend(made)
            if isinstance(node, ast.ClassDef):
                self._body(node.body, (*scope, node.name), reachable, False)
            elif isinstance(node, _Function):
                self._body(node.body, (*scope, node.name), False, True)
            else:
                for inner in _statement_bodies(node):
                    self._body(inner, scope, False, local)

    def _add(self, definition: Definition, node: ast.stmt) -> None:
        self.definitions.append(definition)
        self.nodes[definition] = node


class PythonReading:
    """One Python file, read through its syntax tree."""

    def __init__(self, module: PythonModule | None) -> None:
        self.module = module
        """The parse the framework extractors read too; None when the text does not parse."""

    @property
    def parsed(self) -> bool:
        return self.module is not None

    @cached_property
    def _walk(self) -> _Walk:
        return _Walk(self.module.tree if self.module is not None else None)

    def definitions(self) -> tuple[Definition, ...]:
        """Every function, class and method at any depth, and each name an assignment binds
        that is not a function's local variable, a class attribute included, in source order,
        but for a `try` statement: what its `else` and
        `finally` hold comes before what its handlers hold. A definition inside a function or
        a block, such as an `if`, is not `reachable`, since no dotted path names it."""
        return tuple(self._walk.definitions)

    def imports(self) -> tuple[Import, ...]:
        """Every `import` and `from` import at any depth, a deferred one inside a function
        included, in the order `definitions` has: source order, but for a `try` statement."""
        return tuple(self._walk.imports)

    def places_every_import(self, importer: Path) -> bool:
        """A module is a file under the importing file's package or a source root, or it is
        not this repository's. A text that does not parse has no import read at all."""
        return self.parsed

    def files(self, source: str, importer: Path, roots: Sequence[Path]) -> list[Path]:
        """The `.py` file and the package `__init__.py` that can hold the module `source`
        names: under `importer`'s own package for a relative import, one parent up for each
        dot past the first, and else under each source root."""
        level = len(source) - len(source.lstrip("."))
        module = source[level:]
        parts = module.split(".") if module else []
        if level:
            package = importer.parent
            for _ in range(level - 1):
                package = package.parent
            bases = [package]
        elif parts:
            bases = list(roots)
        else:
            return []
        out: list[Path] = []
        for base in bases:
            out.extend(_module_files(base, parts))
        return out

    def references(self, definition: Definition) -> References:
        """What the body of `definition` reads and binds: a function's parameters count as
        bound. A name bound anywhere in the body, a function nested in it included, counts as
        bound for the whole of it."""
        node = self._walk.nodes.get(definition)
        if node is None:
            return _NOTHING
        loads: set[str] = set()
        attributes: set[tuple[str | None, str]] = set()
        rebound: set[str] = set()
        statements: list[ast.stmt] = [node]
        if isinstance(node, _Function):
            rebound = {arg.arg for arg in ast.walk(node.args) if isinstance(arg, ast.arg)}
            statements = node.body
        elif isinstance(node, ast.ClassDef):
            statements = node.body
        imports: list[Import] = []
        for statement in statements:
            for inner in ast.walk(statement):
                if isinstance(inner, ast.Name):
                    (loads if isinstance(inner.ctx, ast.Load) else rebound).add(inner.id)
                elif isinstance(inner, ast.Attribute):
                    attributes.add((_dotted(inner.value), inner.attr))
                elif isinstance(inner, ast.arg):
                    rebound.add(inner.arg)
                elif isinstance(inner, _Binder):
                    if inner.name:
                        rebound.add(inner.name)
                elif isinstance(inner, ast.MatchMapping):
                    # `case {**rest}:` binds `rest`, which the node carries as a plain string.
                    if inner.rest:
                        rebound.add(inner.rest)
                elif isinstance(inner, _Import):
                    imports.extend(self._walk.by_statement.get(id(inner), ()))
        return References(
            frozenset(loads), frozenset(attributes), frozenset(rebound), tuple(imports)
        )

    def canonical(self, symbol: str | None = None) -> str | None:
        """`_canonical` of the definition `symbol` names, found by `_find_symbol`, or of the
        whole module."""
        if self.module is None:
            return None
        if symbol is None:
            return _canonical(self.module.tree)
        node = _find_symbol(self.module.tree, symbol)
        return None if node is None else _canonical(node)

    def tests(self) -> tuple[Definition, ...]:
        """Each function whose name starts with `test`, at the top level or in a class there,
        at any depth of classes."""
        return tuple(
            d
            for d in self._walk.definitions
            if d.kind == "function" and d.reachable and d.name.startswith("test")
        )


class PythonReader:
    """Reads Python through `ast`, the parser of the interpreter running Irminsul."""

    def read(self, text: str, memo: Memo | None = None) -> PythonReading:
        return PythonReading(PythonModule.parse(text))

    def mentioned_as(self, path: Path) -> frozenset[str]:
        """The module's name: the file's stem, or its directory's for a package's
        `__init__.py`."""
        if path.stem == "__init__" and path.parent.name:
            return frozenset({path.parent.name})
        return frozenset({path.stem})


PYTHON_READER = PythonReader()
