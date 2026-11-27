"""Bind the code names a doc cites to the files that define them.

A doc names code in code spans: `fetchUserSession()`, `SESSION_TTL`, `store.flush`. When
no surface extractor, symbol index, or repository path resolves such a name, and no
anchor in the doc binds it, the name is unbound. Deciding which file the doc meant is a
judgment, so this module only finds unbound names and ranks the files that contain them;
an agent chooses one and writes the anchor.

A name that does resolve, to one function or class, can be bound to more than its
definition: a sentence that says what the code does is best anchored to the test that
asserts it. So this module also finds the test functions that name such a definition. Which
of them asserts the sentence is again a judgment, made by seeing the test fail.

What a file defines, which of its functions are tests, and what a test's body and imports
refer to are each asked of the reader of the file's language (`irminsul.languages`).
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from irminsul.anchors import Anchor, defines, definition_line, parse_anchors, resolve
from irminsul.checks.globs import resolve_display_path
from irminsul.code_references import CodeResolver
from irminsul.languages import reader_for
from irminsul.languages.reader import Import, References
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
    """Definitions a reader found inside a function or a block, which no anchor can name."""


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

    In a file whose language has a reader, a definition is what that reader finds, so a
    class member is offered under its dotted path, and a file that does not parse offers
    nothing. Any other file resolves by text, so there the line that looks like a
    definition is offered, else the first mention. Mentions are offered only when nothing
    defines the name: a file that merely names it is the wrong place to bind.
    """
    leaf = name.rsplit(".", 1)[-1]
    token = re.compile(rf"(?<![\w$]){re.escape(leaf)}(?![\w$])")
    definitions: list[Candidate] = []
    mentions: list[Candidate] = []
    unreachable: list[Candidate] = []
    for display, lines in sources:
        if not any(token.search(line) for line in lines):
            continue
        code_reader = reader_for(display)
        if code_reader is not None:
            for found in code_reader.read("\n".join(lines)).definitions():
                if found.name == leaf:
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
    """A function or class a doc names: the display path of the file that defines it, the
    line of its definition there, and its bare name. Two methods of one name in one file
    differ by their line."""

    path: str
    line: int
    name: str


def named_definition(span: str, resolver: CodeResolver) -> Definition | None:
    """The one function or class a code span resolves to, or None.

    A span a surface resolves, such as a command or an option, names that surface and not
    a definition, and a name two definitions share resolves to neither.
    """
    for ref in resolver.resolve(span):
        if ref.kind == "symbol" and ref.line is not None:
            return Definition(ref.defined_at, ref.line, ref.identity)
    return None


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


def _key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.fspath(path)))


class _TestReader:
    """The test files of one graph, each read at most once by its language's reader, and
    what their imports bind."""

    def __init__(self, graph: DocGraph) -> None:
        assert graph.config is not None and graph.repo_root is not None
        self._source = graph.source
        self._source_roots = graph.config.paths.source_roots
        self._repo_root = graph.repo_root
        self._roots = [graph.repo_root / root for root in self._source_roots]
        self._test_files = {display: path for path, display in graph.source.test_walk.files}
        self._source_files = {display: path for path, display in graph.source.files}
        self._functions: dict[str, list[tuple[CandidateTest, References]]] = {}
        self._file_imports: dict[tuple[str, str], _Imports] = {}

    def module_key(self, definition: Definition) -> str:
        """The file that defines `definition`, spelled as `imports` spells a file, which is
        how `Ranker.importers` spells it too."""
        path = resolve_display_path(self._repo_root, self._source_roots, definition.path)
        return _key(path if path is not None else self._repo_root / definition.path)

    def owner(self, definition: Definition) -> str | None:
        """The class whose body defines `definition`, or None for one at the top level."""
        path = self._source_files.get(definition.path)
        reading = self._source.reading(path) if path is not None else None
        if reading is None:
            return None
        return next(
            (
                found.holder
                for found in reading.definitions()
                if (found.line, found.name) == (definition.line, definition.name)
            ),
            None,
        )

    def functions(self, display: str) -> list[tuple[CandidateTest, References]]:
        """The test functions of one test file, each with what its body refers to and
        binds; none when it does not parse."""
        if display not in self._functions:
            reading = self._source.reading(self._test_files[display])
            self._functions[display] = (
                []
                if reading is None
                else [
                    (CandidateTest(display, test.line, test.symbol), reading.references(test))
                    for test in reading.tests()
                ]
            )
        return self._functions[display]

    def file_imports(self, display: str, module_key: str) -> _Imports:
        """What the imports of a test file outside every function and class bind of the
        module in the file `module_key`. They are read from the last line to the first, so
        of two that bind one name the first in the file is kept, where Python keeps the
        last."""
        key = (display, module_key)
        if key not in self._file_imports:
            reading = self._source.reading(self._test_files[display])
            imports = reading.imports() if reading is not None else ()
            outside = sorted(
                (found for found in imports if not found.scope), key=lambda found: found.line
            )
            self._file_imports[key] = self.imports(reversed(outside), display, module_key)
        return self._file_imports[key]

    def imports(self, imports: Iterable[Import], display: str, module_key: str) -> _Imports:
        """What `imports`, imports of the test file `display`, bind of the module in the
        file `module_key`, each resolved to files by the file's reader, as `imported_files`
        resolves an import."""
        names: dict[str, str] = {}
        star = False
        modules: set[str] = set()
        others: set[str] = set()
        importer = self._test_files[display]
        reading = self._source.reading(importer)
        if reading is None:
            return _Imports(names, star, frozenset(), frozenset())
        files = reading.files

        def is_the_module(source: str) -> bool:
            return any(_key(path) == module_key for path in files(source, importer, self._roots))

        for found in imports:
            from_the_module = is_the_module(found.source)
            for name in found.names:
                if name.name is None:
                    if from_the_module:
                        modules.add(name.reached_as)
                    else:
                        others.add(name.local)
                elif from_the_module and name.name == "*":
                    star = True
                elif from_the_module:
                    names[name.local] = name.name
                elif name.source is not None and is_the_module(name.source):
                    modules.add(name.reached_as)
                elif name.name != "*":
                    others.add(name.local)
        return _Imports(names, star, frozenset(modules), frozenset(others))


def _names(refs: References, imports: _Imports, name: str, owner: str | None) -> bool:
    """Whether a test function, whose body refers to and binds `refs`, refers to a
    definition through `imports`, what its file and its own body import of the defining
    module.

    A function or class at the top level of its module is referred to by a name imported
    from the module, under an alias too, that the test does not bind itself, or as an
    attribute of an expression that is the module. A method is referred to by an attribute
    of its name, in a test whose imports reach its class or its module: a reader does not
    say what class the object it is read from has, so that much stays a reading by name.
    """
    if owner is not None:
        reaches = imports.star or owner in imports.names.values() or bool(imports.modules)
        return reaches and any(attribute == name for _, attribute in refs.attributes)
    shadowed = refs.bound | (imports.others - set(imports.names))
    bound = {local for local, original in imports.names.items() if original == name}
    if imports.star:
        bound.add(name)
    if refs.names & (bound - shadowed):
        return True
    return any(
        attribute == name and value in imports.modules and value.split(".", 1)[0] not in refs.bound
        for value, attribute in refs.attributes
        if value is not None
    )


def naming_tests(
    graph: DocGraph, definitions: Collection[Definition]
) -> dict[Definition, list[CandidateTest]]:
    """The test functions that name each of `definitions`, at most three, by path and line.

    A test function is one its file's reader says is a test, for Python a function whose
    name starts with `test`, in a file under `paths.test_roots` that imports the defining
    module, which is the reading `Ranker.importers` makes for the context packet. It names
    the definition when its body refers to it through the imports of its file or its own
    body, as `_names` reads them, so a parameter, a fixture or a local variable that is
    merely spelled the same names nothing. That is a reading of the code and runs nothing:
    a test that reaches the code through a helper, a fixture or a command line is not
    found. A test file that does not parse is skipped.
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
            for test, refs in reader.functions(display):
                imports = of_the_file
                if refs.imports:
                    imports = imports.within(reader.imports(refs.imports, display, module_key))
                if _names(refs, imports, definition.name, owner):
                    found.append(test)
        found.sort(key=lambda test: (test.path, test.line))
        out[definition] = found[:_SUGGESTION_LIMIT]
    return out
