"""Bind the code names a doc cites to the files that define them.

A doc names code in code spans: `fetchUserSession()`, `SESSION_TTL`, `store.flush`. When
no surface extractor, symbol index, or repository path resolves such a name, and no
anchor in the doc binds it, the name is unbound. Deciding which file the doc meant is a
judgment, so this module only finds unbound names and ranks the files that contain them;
an agent chooses one and writes the anchor.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from irminsul.anchors import Anchor, defines, definition_line, parse_anchors, resolve
from irminsul.checks.globs import walk_configured_source_files
from irminsul.code_references import CodeResolver
from irminsul.config import IrminsulConfig

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

    def marker(self, name: str) -> str:
        return f"<!-- anchor: {self.path}#{name} -->"


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


def load_sources(repo_root: Path, config: IrminsulConfig) -> Sources:
    """Each readable source file's display path and lines, read once for many names."""
    out: Sources = []
    for abs_path, display in walk_configured_source_files(repo_root, config).files:
        try:
            out.append((display, abs_path.read_text(encoding="utf-8").splitlines()))
        except (OSError, UnicodeDecodeError):
            continue
    return out


def suggest(repo_root: Path, sources: Sources, name: str) -> list[Candidate]:
    """Source files an anchor for `name` resolves in, definition-like lines first."""
    leaf = name.rsplit(".", 1)[-1]
    token = re.compile(rf"(?<![\w$]){re.escape(leaf)}(?![\w$])")
    found: list[Candidate] = []
    for display, lines in sources:
        if not any(token.search(line) for line in lines):
            continue
        anchor = Anchor(line=0, raw="", path=display, symbol=name, pinned=None)
        if resolve(repo_root, anchor).status != "ok":
            continue
        index = definition_line(lines, leaf)
        if index is not None:
            found.append(Candidate(display, index + 1, defines(lines[index], leaf)))
    found.sort(key=lambda c: (not c.definition, c.path))
    return found[:_SUGGESTION_LIMIT]
