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
import re
import sys
from collections.abc import Collection, Iterator
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
from irminsul.code_references import CodeResolver, Reference
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


def named_definition(span: str, resolver: CodeResolver) -> Reference | None:
    """The one Python function or class a code span resolves to, or None.

    A span a surface resolves, such as a command or an option, names that surface and not
    a definition, and a name two definitions share resolves to neither.
    """
    return next((ref for ref in resolver.resolve(span) if ref.kind == "symbol"), None)


def _test_functions(
    body: list[ast.stmt], scope: tuple[str, ...] = ()
) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Each function whose name starts with `test`, with the dotted path an anchor names it
    by: one at the top level of `body` or in a class there, at any depth of classes. One
    inside a function or a block is left out, as no anchor reaches it."""
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("test"):
                yield ".".join([*scope, node.name]), node
        elif isinstance(node, ast.ClassDef):
            yield from _test_functions(node.body, (*scope, node.name))


def _body_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    """Every identifier the body uses: a bare name, or the last part of a dotted one."""
    out: set[str] = set()
    for statement in function.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name):
                out.add(node.id)
            elif isinstance(node, ast.Attribute):
                out.add(node.attr)
    return frozenset(out)


def naming_tests(
    graph: DocGraph, definitions: Collection[tuple[str, str]]
) -> dict[tuple[str, str], list[CandidateTest]]:
    """The test functions that name each of `definitions`, at most three, by path and line.

    A definition is a source file's display path and the name of a Python function or class
    in it. A test function is a function whose name starts with `test`, in a Python file
    under `paths.test_roots` that imports the defining module, which is the reading
    `Ranker.importers` makes for the context packet. It names the definition when its body
    uses that name as an identifier, bare or as the last part of a dotted one. That is a
    reading of the syntax tree and runs nothing: a test that reaches the code through a
    helper, a fixture or a command line is not found, and one that uses the same name on
    another object is. A test file that does not parse is skipped.
    """
    importers = Ranker(graph).importers(sorted({path for path, _ in definitions}))
    test_files = {display: path for path, display in graph.source.test_walk.files}
    functions: dict[str, list[tuple[CandidateTest, frozenset[str]]]] = {}
    out: dict[tuple[str, str], list[CandidateTest]] = {}
    for path, name in definitions:
        found: list[CandidateTest] = []
        for display in importers[path]:
            if display not in functions:
                module = graph.source.module(test_files[display])
                functions[display] = (
                    []
                    if module is None
                    else [
                        (CandidateTest(display, node.lineno, symbol), _body_names(node))
                        for symbol, node in _test_functions(module.tree.body)
                    ]
                )
            found.extend(test for test, names in functions[display] if name in names)
        found.sort(key=lambda test: (test.path, test.line))
        out[path, name] = found[:_SUGGESTION_LIMIT]
    return out
