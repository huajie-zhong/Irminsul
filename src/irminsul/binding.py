"""Bind the code names a doc cites to the files that define them.

A doc names code in code spans: `fetchUserSession()`, `SESSION_TTL`, `store.flush`. When
no surface extractor, symbol index, or repository path resolves such a name, and no
anchor in the doc binds it, the name is unbound. Deciding which file the doc meant is a
judgment, so this module only finds unbound names and ranks the files that contain them;
an agent chooses one and writes the anchor.
"""

from __future__ import annotations

import ast
import re
import sys
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
from irminsul.code_references import CodeResolver

if TYPE_CHECKING:
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
    """The code names among `spans` that nothing resolves and no anchor binds."""
    out: list[str] = []
    for span in spans:
        name = code_name(span)
        if name is None or name in bound or name.rsplit(".", 1)[-1] in bound:
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
