"""Bind the code names a doc cites to the files that define them.

A doc names code in code spans: `fetchUserSession()`, `SESSION_TTL`, `store.flush`. When
no surface extractor, symbol index, or repository path resolves such a name, and no
anchor in the doc binds it, the name is unbound. Deciding which file the doc meant is a
judgment, so this module only finds unbound names and ranks the files that contain them;
an agent chooses one and writes the anchor.

A name that does resolve, to one Python function or class, can be bound to more than its
definition: a sentence that says what the code does is best anchored to the test that
asserts it. So this module also finds the test functions that name such a definition. Which
of them asserts the sentence is again a judgment, made by seeing the test fail.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from irminsul.anchors import (
    Anchor,
    defines,
    definition_line,
    parse_anchors,
    python_definitions,
    resolve,
)
from irminsul.checks.dependency_check import imported_paths
from irminsul.checks.globs import resolve_display_path
from irminsul.code_references import CodeResolver
from irminsul.inventory.base import PythonModule
from irminsul.ranked_tests import Ranker

if TYPE_CHECKING:
    from irminsul.docgraph import DocGraph
    from irminsul.source_tree import SourceTree

_NAME_RE = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*(?:\(\))?$")
_CAMEL_RE = re.compile(r"[a-z0-9][A-Z]")
_FILE_SUFFIXES = frozenset(
    [
        "md",
        "mdx",
        "rst",
        "txt",
        "py",
        "toml",
        "json",
        "yaml",
        "yml",
        "ini",
        "cfg",
        "lock",
        "env",
        "ts",
        "tsx",
        "js",
        "jsx",
        "mjs",
        "cjs",
        "go",
        "rs",
        "rb",
        "java",
        "kt",
        "cs",
        "c",
        "h",
        "cpp",
        "hpp",
        "swift",
        "php",
        "lua",
        "sh",
        "ps1",
        "sql",
        "csv",
        "xml",
        "html",
        "css",
        "scss",
    ]
)
_NOT_OURS = frozenset({*sys.stdlib_module_names, "self", "cls", "this"})
_SUGGESTION_LIMIT = 3


@dataclass(frozen=True)
class Candidate:
    path: str
    line: int
    definition: bool
    symbol: str | None = None
    """The name to anchor when it differs from the cited one, such as `Store.flush`."""

    def marker(self, name: str) -> str:
        return f"<!-- anchor: {self.path}#{self.symbol or name} -->"


@dataclass(frozen=True)
class Suggestions:
    candidates: list[Candidate]
    """Markers that resolve: definitions, or mentions when nothing defines the name."""
    unreachable: list[Candidate]
    """Python definitions inside a function or a block, which no anchor can name."""


def code_name(span: str) -> str | None:
    """The name a code span cites, when the span can only be a code name."""
    text = span.strip()
    if not _NAME_RE.match(text):
        return None
    name = text.removesuffix("()")
    if "." in name and (
        name.rsplit(".", 1)[-1].lower() in _FILE_SUFFIXES or name.split(".", 1)[0] in _NOT_OURS
    ):
        return None
    distinctive = (
        text.endswith("()") or "_" in name or "." in name or _CAMEL_RE.search(name) is not None
    )
    return name if distinctive else None


def bound_names(text: str) -> set[str]:
    """Names an anchor in `text` binds, both dotted and by their last part."""
    out: set[str] = set()
    for anchor in parse_anchors(text):
        if anchor.symbol:
            out.add(anchor.symbol)
            out.add(anchor.symbol.rsplit(".", 1)[-1])
    return out


def unbound_names(spans: list[str], resolver: CodeResolver, bound: set[str]) -> list[str]:
    """The code names among `spans` that nothing resolves and no anchor binds.

    A name the language itself defines is bound to the language, so it is never unbound.
    """
    out: list[str] = []
    for span in spans:
        name = code_name(span)
        if name is None or name in bound or name.rsplit(".", 1)[-1] in bound:
            continue
        if name.split(".", 1)[0] in resolver.builtins:
            continue
        if resolver.resolve(span):
            continue
        if name not in out:
            out.append(name)
    return out


Sources = list[tuple[str, list[str]]]


def load_sources(tree: SourceTree) -> Sources:
    """Each readable source file's display path and lines, read once for many names."""
    out: Sources = []
    for abs_path, display in tree.files:
        text = tree.text(abs_path)
        if text is not None:
            out.append((display, text.splitlines()))
    return out


def suggest(repo_root: Path, sources: Sources, name: str) -> Suggestions:
    """Where an anchor for `name` could point, definitions first.

    A Python definition is found in the syntax tree, so a class member is offered under
    its dotted path. Another language resolves by text, so there the line that looks
    like a definition is offered, else the first mention. Mentions are offered only when
    nothing defines the name: a file that merely names it is the wrong place to bind.
    """
    leaf = name.rsplit(".", 1)[-1]
    token = re.compile(rf"(?<![\w$]){re.escape(leaf)}(?![\w$])")
    definitions: list[Candidate] = []
    mentions: list[Candidate] = []
    unreachable: list[Candidate] = []
    for display, lines in sources:
        if not any(token.search(line) for line in lines):
            continue
        if display.endswith(".py"):
            try:
                tree = ast.parse("\n".join(lines))
            except SyntaxError:
                continue
            for found in python_definitions(tree, leaf):
                candidate = Candidate(display, found.line, True, found.symbol)
                (definitions if found.reachable else unreachable).append(candidate)
            continue
        anchor = Anchor(line=0, raw="", path=display, symbol=name, pinned=None)
        if resolve(repo_root, anchor).status != "ok":
            continue
        index = definition_line(lines, leaf)
        if index is not None:
            is_definition = defines(lines[index], leaf)
            (definitions if is_definition else mentions).append(
                Candidate(display, index + 1, is_definition)
            )
    chosen = definitions or ([] if unreachable else mentions)
    chosen.sort(key=lambda c: (c.path, c.line))
    return Suggestions(chosen[:_SUGGESTION_LIMIT], unreachable[:_SUGGESTION_LIMIT])


@dataclass(frozen=True)
class CandidateTest:
    """A test function an anchor can name."""

    path: str
    line: int
    symbol: str
    """The dotted path from the module to the function, such as `TestFees.test_cap`."""

    @property
    def marker(self) -> str:
        return f"<!-- anchor: {self.path}#{self.symbol} -->"


@dataclass(frozen=True)
class Definition:
    """A Python function or class a doc names: the display path of the file that defines
    it, the line of its definition there, and its bare name. Two methods of one name in one
    file differ by their line."""

    path: str
    line: int
    name: str


def named_definition(span: str, resolver: CodeResolver) -> Definition | None:
    """The one Python function or class a code span resolves to, or None.

    A span a surface resolves, such as a command or an option, names that surface and not
    a definition, and a name two definitions share resolves to neither.
    """
    for ref in resolver.resolve(span):
        if ref.kind == "symbol" and ref.line is not None:
            return Definition(ref.defined_at, ref.line, ref.identity)
    return None


_Function = ast.FunctionDef | ast.AsyncFunctionDef
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_Import = ast.Import | ast.ImportFrom
#: The nodes that bind the name they carry: a nested definition, an `except ... as` name,
#: and a `match` capture.
_Binder = _Function | ast.ClassDef | ast.ExceptHandler | ast.MatchAs | ast.MatchStar


@dataclass(frozen=True)
class _Imports:
    """What some import statements of a test file bind of one source module."""

    names: dict[str, str]
    """Each local name imported from the module, and the module's name for it."""
    star: bool
    """Whether they import every name of the module."""
    modules: frozenset[str]
    """The expressions that are the module itself, such as `policy` or `loans.policy`."""
    others: frozenset[str]
    """The local names they bind to anything else."""

    def within(self, inner: _Imports) -> _Imports:
        """These, a file's imports, as seen by a function whose body imports `inner`: a name
        the body imports from elsewhere is no longer the module's."""
        return _Imports(
            {
                **{local: name for local, name in self.names.items() if local not in inner.others},
                **inner.names,
            },
            self.star or inner.star,
            self.modules | inner.modules,
            (self.others - set(inner.names)) | inner.others,
        )


@dataclass(frozen=True)
class _TestFunction:
    """One test function, read once for every definition it may name."""

    test: CandidateTest
    loads: frozenset[str]
    """The bare names its body reads."""
    attributes: frozenset[tuple[str | None, str]]
    """Each attribute its body reads, with the dotted name it is read from, or None when it
    is read from anything else, such as a call's result."""
    rebound: frozenset[str]
    """The names it binds itself: a parameter, a fixture, an assignment, a loop or `with`
    target, a nested definition. A bare use of one is of its own value."""
    imports: tuple[ast.Import | ast.ImportFrom, ...]
    """The import statements in its body, which bind for it alone."""


def _key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.fspath(path)))


def _dotted(node: ast.expr) -> str | None:
    """`a.b.c` for a chain of attributes that starts at a bare name, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def _scope_nodes(nodes: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """Every node of one scope: a function, class or lambda in it is yielded, not entered."""
    stack = list(nodes)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def _test_functions(
    body: list[ast.stmt], scope: tuple[str, ...] = ()
) -> Iterator[tuple[str, _Function]]:
    """Each function whose name starts with `test`, with the dotted path an anchor names it
    by: one at the top level of `body` or in a class there, at any depth of classes. One
    inside a function or a block is left out, as no anchor reaches it."""
    for node in body:
        if isinstance(node, _Function):
            if node.name.startswith("test"):
                yield ".".join([*scope, node.name]), node
        elif isinstance(node, ast.ClassDef):
            yield from _test_functions(node.body, (*scope, node.name))


def _read_function(display: str, symbol: str, function: _Function) -> _TestFunction:
    """What one test function's body reads and binds. A name bound anywhere in the body,
    a function nested in it included, counts as bound for the whole of it: that can miss a
    test, and never offers one that does not name the definition."""
    loads: set[str] = set()
    attributes: set[tuple[str | None, str]] = set()
    rebound = {node.arg for node in ast.walk(function.args) if isinstance(node, ast.arg)}
    imports: list[ast.Import | ast.ImportFrom] = []
    for statement in function.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name):
                (loads if isinstance(node.ctx, ast.Load) else rebound).add(node.id)
            elif isinstance(node, ast.Attribute):
                attributes.add((_dotted(node.value), node.attr))
            elif isinstance(node, ast.arg):
                rebound.add(node.arg)
            elif isinstance(node, _Binder):
                if node.name:
                    rebound.add(node.name)
            elif isinstance(node, ast.MatchMapping):
                # `case {**rest}:` binds `rest`, which the node carries as a plain string.
                if node.rest:
                    rebound.add(node.rest)
            elif isinstance(node, _Import):
                imports.append(node)
    return _TestFunction(
        CandidateTest(display, function.lineno, symbol),
        frozenset(loads),
        frozenset(attributes),
        frozenset(rebound),
        tuple(imports),
    )


class _TestReader:
    """The test files of one graph, each read at most once, and what their imports bind."""

    def __init__(self, graph: DocGraph) -> None:
        assert graph.config is not None and graph.repo_root is not None
        self._source = graph.source
        self._roots = graph.config.paths.source_roots
        self._repo_root = graph.repo_root
        self._test_files = {display: path for path, display in graph.source.test_walk.files}
        self._source_files = {display: path for path, display in graph.source.files}
        self._functions: dict[str, list[_TestFunction]] = {}
        self._file_imports: dict[tuple[str, str], _Imports] = {}

    def module_key(self, definition: Definition) -> str:
        """The file that defines `definition`, spelled as `_loads` spells a file, which is
        how `Ranker.importers` spells it too."""
        path = resolve_display_path(self._repo_root, self._roots, definition.path)
        return _key(path if path is not None else self._repo_root / definition.path)

    def owner(self, definition: Definition) -> str | None:
        """The class whose body defines `definition`, or None for one at the top level."""
        path = self._source_files.get(definition.path)
        module = self._source.module(path) if path is not None else None
        for node in module.tree.body if module is not None else []:
            if isinstance(node, ast.ClassDef) and any(
                isinstance(member, _Function | ast.ClassDef)
                and member.lineno == definition.line
                and member.name == definition.name
                for member in node.body
            ):
                return node.name
        return None

    def functions(self, display: str) -> list[_TestFunction]:
        """The test functions of one test file; none when it does not parse."""
        if display not in self._functions:
            module = self._source.module(self._test_files[display])
            self._functions[display] = (
                []
                if module is None
                else [
                    _read_function(display, symbol, function)
                    for symbol, function in _test_functions(module.tree.body)
                ]
            )
        return self._functions[display]

    def file_imports(self, display: str, module_key: str) -> _Imports:
        """What the imports of a test file outside every function and class bind of the
        module in the file `module_key`."""
        key = (display, module_key)
        if key not in self._file_imports:
            module = self._source.module(self._test_files[display])
            statements = [
                node
                for node in _scope_nodes(module.tree.body if module is not None else [])
                if isinstance(node, _Import)
            ]
            self._file_imports[key] = self.imports(statements, display, module_key)
        return self._file_imports[key]

    def imports(
        self, statements: Iterable[ast.Import | ast.ImportFrom], display: str, module_key: str
    ) -> _Imports:
        """What `statements`, import statements of the test file `display`, bind of the
        module in the file `module_key`, read as `imported_paths` reads an import."""
        names: dict[str, str] = {}
        star = False
        modules: set[str] = set()
        others: set[str] = set()
        importer = self._test_files[display]
        for node in statements:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if module_key in self._loads(ast.Import(names=[alias]), importer):
                        modules.add(alias.asname or alias.name)
                    else:
                        others.add(alias.asname or alias.name.split(".", 1)[0])
                continue
            bare = ast.ImportFrom(module=node.module, names=[], level=node.level)
            from_the_module = module_key in self._loads(bare, importer)
            for alias in node.names:
                local = alias.asname or alias.name
                if from_the_module and alias.name == "*":
                    star = True
                elif from_the_module:
                    names[local] = alias.name
                elif module_key in self._loads(
                    ast.ImportFrom(module=node.module, names=[alias], level=node.level), importer
                ):
                    modules.add(local)
                elif alias.name != "*":
                    others.add(local)
        return _Imports(names, star, frozenset(modules), frozenset(others))

    def _loads(self, statement: ast.Import | ast.ImportFrom, importer: Path) -> set[str]:
        """The files one import statement may load."""
        module = PythonModule(ast.Module(body=[statement], type_ignores=[]))
        return {
            _key(path) for path in imported_paths(module, importer, self._roots, self._repo_root)
        }


def _names(function: _TestFunction, imports: _Imports, name: str, owner: str | None) -> bool:
    """Whether a test function's body refers to a definition through `imports`, what its
    file and its own body import of the defining module.

    A function or class at the top level of its module is referred to by a name imported
    from the module, under an alias too, that the test does not bind itself, or as an
    attribute of an expression that is the module. A method is referred to by an attribute
    of its name, in a test whose imports reach its class or its module: the syntax tree
    does not say what class the object it is read from has, so that much stays a reading
    by name.
    """
    if owner is not None:
        reaches = imports.star or owner in imports.names.values() or bool(imports.modules)
        return reaches and any(attribute == name for _, attribute in function.attributes)
    shadowed = function.rebound | (imports.others - set(imports.names))
    bound = {local for local, original in imports.names.items() if original == name}
    if imports.star:
        bound.add(name)
    if function.loads & (bound - shadowed):
        return True
    return any(
        attribute == name
        and value in imports.modules
        and value.split(".", 1)[0] not in function.rebound
        for value, attribute in function.attributes
        if value is not None
    )


def naming_tests(
    graph: DocGraph, definitions: Collection[Definition]
) -> dict[Definition, list[CandidateTest]]:
    """The test functions that name each of `definitions`, at most three, by path and line.

    A test function is a function whose name starts with `test`, in a Python file under
    `paths.test_roots` that imports the defining module, which is the reading
    `Ranker.importers` makes for the context packet. It names the definition when its body
    refers to it through the imports of its file or its own body, as `_names` reads them,
    so a parameter, a fixture or a local variable that is merely spelled the same names
    nothing. That is a reading of the syntax tree and runs nothing: a test that reaches the
    code through a helper, a fixture or a command line is not found. A test file that does
    not parse is skipped.
    """
    reader = _TestReader(graph)
    importers = Ranker(graph).importers(sorted({definition.path for definition in definitions}))
    out: dict[Definition, list[CandidateTest]] = {}
    for definition in definitions:
        module_key = reader.module_key(definition)
        owner = reader.owner(definition)
        found: list[CandidateTest] = []
        for display in importers[definition.path]:
            of_the_file = reader.file_imports(display, module_key)
            for function in reader.functions(display):
                imports = of_the_file
                if function.imports:
                    imports = imports.within(reader.imports(function.imports, display, module_key))
                if _names(function, imports, definition.name, owner):
                    found.append(function.test)
        found.sort(key=lambda test: (test.path, test.line))
        out[definition] = found[:_SUGGESTION_LIMIT]
    return out
