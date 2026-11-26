"""Resolve names written in docs to where they are defined in code.

Shared by the review queue, which pairs a sentence with the code it names, and by the
`code-references` check, which reports a name that resolves to nothing.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from irminsul.checks.code_spans import mention_regex
from irminsul.git.blame import LineTimes
from irminsul.git.mtime import last_commit_time_any_repo
from irminsul.inventory import SurfaceItem, available_kinds, kind_capabilities
from irminsul.inventory.base import SourceReader
from irminsul.inventory.cli_options import command_options
from irminsul.inventory.programs import program_names
from irminsul.languages import LANGUAGE_REGISTRY
from irminsul.languages.python import PYTHON_PROFILE

if TYPE_CHECKING:
    from irminsul.git.reader import GitReader
    from irminsul.source_tree import SourceTree

# An identity is named in plain prose only when it cannot be an ordinary word.
_DISTINCTIVE_RE = re.compile(r"^[A-Za-z0-9-]*[-_.][A-Za-z0-9_.-]*[A-Za-z0-9]$")
_TOKEN_EDGE = "A-Za-z0-9_-"
_FLAG_RE = re.compile(r"(?<![\w-])--[a-z0-9][a-z0-9-]*(?![\w-])")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:\(\))?$")


@dataclass(frozen=True)
class Reference:
    span: str
    kind: str
    identity: str
    defined_at: str
    line: int | None
    line_end: int | None = None


class CodeResolver:
    def __init__(self, tree: SourceTree, *, tracked: frozenset[str] | None = None) -> None:
        """Pair names with the code `tree` holds.

        `tracked` is given for a tree that is one commit's: the repository paths that commit
        holds, which then say whether a span names a file, where the disk otherwise does.
        """
        repo_root, config = tree.repo_root, tree.config
        self._tracked = tracked
        self.builtins: frozenset[str] = frozenset().union(
            *(LANGUAGE_REGISTRY[name].builtins for name in config.languages.enabled)
        )
        self._repo_root = repo_root
        files = tree.files
        self._reader: SourceReader = tree
        self._abs_by_display = {display: abs_path for abs_path, display in files}
        self._command_blocks: dict[str, str] | None = None
        self._command_flags: dict[str, frozenset[str]] | None = None
        self._source_tokens: set[str] | None = None
        self._functions: dict[str, list[tuple[int, int]]] = {}
        self.surfaces: dict[str, dict[str, SurfaceItem]] = {}
        self.mentions: dict[str, list[re.Pattern[str]]] = {}
        self.command_kinds: set[str] = set()
        names = program_names(repo_root, config)
        self.program_prefix = (
            re.compile(rf"^(?:{'|'.join(re.escape(n) for n in names)})\s+") if names else None
        )
        for kind in available_kinds(config):
            capabilities = kind_capabilities(kind, config)
            if capabilities.mention_patterns:
                self.mentions[kind] = [mention_regex(p) for p in capabilities.mention_patterns]
            if capabilities.command_path:
                self.command_kinds.add(kind)
            items = tree.surface(kind)
            if items:
                self.surfaces[kind] = {item.identity: item for item in items}
        self._symbols = self._symbol_index(files, tree)
        self._plain: list[tuple[str, re.Pattern[str]]] = []
        for kind, surface in self.surfaces.items():
            distinctive = sorted(
                (identity for identity in surface if _DISTINCTIVE_RE.match(identity)),
                key=len,
                reverse=True,
            )
            if distinctive:
                alternatives = "|".join(re.escape(identity) for identity in distinctive)
                self._plain.append(
                    (
                        kind,
                        re.compile(rf"(?<![{_TOKEN_EDGE}])(?:{alternatives})(?![{_TOKEN_EDGE}])"),
                    )
                )

    def resolve_prose(self, text: str) -> list[Reference]:
        """Distinctive identities named outside code spans, such as a hyphenated check name."""
        refs: list[Reference] = []
        for kind, pattern in self._plain:
            for match in pattern.finditer(text):
                refs.append(self._ref(match.group(0), kind, self.surfaces[kind][match.group(0)]))
        return refs

    @staticmethod
    def _symbol_index(
        files: list[tuple[Path, str]], reader: SourceReader
    ) -> dict[str, list[tuple[str, int, int]]]:
        """Python definitions by bare name and by `Class.name`."""
        index: dict[str, list[tuple[str, int, int]]] = {}
        for module, display in reader.python_modules(files):
            tree = module.tree
            scopes: list[tuple[str, list[ast.stmt]]] = [("", tree.body)] + [
                (f"{n.name}.", n.body) for n in tree.body if isinstance(n, ast.ClassDef)
            ]
            for prefix, scope in scopes:
                for node in scope:
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                        where = (display, node.lineno, node.end_lineno or node.lineno)
                        index.setdefault(node.name, []).append(where)
                        if prefix:
                            index.setdefault(f"{prefix}{node.name}", []).append(where)
        return index

    def appears_in_source(self, name: str) -> bool:
        """Whether `name` occurs as a whole identifier in any source file; a shell `$NAME`
        counts."""
        if self._source_tokens is None:
            tokens: set[str] = set()
            for abs_path in self._abs_by_display.values():
                text = self._reader.text(abs_path)
                if text is not None:
                    tokens.update(_IDENTIFIER_RE.findall(text))
            self._source_tokens = tokens
        return name in self._source_tokens

    def command_blocks(self) -> dict[str, str]:
        """Each command's definition text, read from where the command extractor found it."""
        if self._command_blocks is not None:
            return self._command_blocks
        from irminsul.anchors import text_block

        blocks: dict[str, str] = {}
        lines_by_file: dict[str, list[str]] = {}
        for kind in self.command_kinds:
            for identity, item in self.surfaces.get(kind, {}).items():
                if item.display is None or item.line is None:
                    continue
                if item.display not in lines_by_file:
                    abs_path = self._abs_by_display.get(item.display)
                    text = (self._reader.text(abs_path) if abs_path else None) or ""
                    lines_by_file[item.display] = text.splitlines()
                lines = lines_by_file[item.display]
                if 0 < item.line <= len(lines):
                    blocks[identity] = "\n".join(text_block(lines, item.line - 1))
        self._command_blocks = blocks
        return blocks

    def command_flags(self) -> dict[str, frozenset[str]]:
        """The long options each command declares.

        A Python function is read as the `cli-options` extractor reads it, so an option
        declared through an alias or by a default value counts. A command defined any other
        way is read from the long options its definition text writes.
        """
        if self._command_flags is None:
            blocks = self.command_blocks()
            flags: dict[str, frozenset[str]] = {}
            for kind in self.command_kinds:
                for identity, item in self.surfaces.get(kind, {}).items():
                    declared = self._declared_options(item)
                    if declared is None and identity in blocks:
                        declared = frozenset(_FLAG_RE.findall(blocks[identity]))
                    if declared is not None:
                        flags[identity] = declared
            self._command_flags = flags
        return self._command_flags

    def _declared_options(self, item: SurfaceItem) -> frozenset[str] | None:
        if item.display is None or item.line is None:
            return None
        abs_path = self._abs_by_display.get(item.display)
        module = self._reader.module(abs_path) if abs_path else None
        return None if module is None else command_options(module, item.line)

    def defines_symbol(self, name: str) -> bool | None:
        """Whether a Python function or class of this name exists; None with no Python source."""
        if not self._symbols:
            return None
        return name in self._symbols

    def strip_program(self, span: str) -> tuple[str, bool]:
        text = span.strip()
        if self.program_prefix is None:
            return text, False
        stripped = self.program_prefix.sub("", text, count=1)
        return stripped, stripped != text

    def resolve(self, span: str) -> list[Reference]:
        """Where the code a span names is defined.

        An option is found by its mention pattern, a command by the longest identity the span
        begins with, and any other configured surface kind by exactly its identity or a dotted
        path ending in it, with or without a trailing `()`. Only a span no surface matches is
        tried as a Python function or class by name, which resolves when one definition has
        that name, and then as a repository file by path, inside a source root or not.
        """
        text, _ = self.strip_program(span)
        refs: list[Reference] = []
        for kind, regexes in self.mentions.items():
            for regex in regexes:
                for match in regex.finditer(text):
                    item = self.surfaces.get(kind, {}).get(match.group(0))
                    if item is not None:
                        refs.append(self._ref(span, kind, item))
        words = text.split()
        for kind, items in self.surfaces.items():
            if kind in self.mentions:
                continue
            if kind in self.command_kinds:
                best = max(
                    (i for i in items if words[: len(i.split())] == i.split()),
                    key=len,
                    default=None,
                )
            else:
                # Configured kinds are often ordinary words, so only a span that is the
                # identity, or a dotted path ending in it, names one.
                leaf = text.removesuffix("()").rsplit(".", 1)[-1]
                best = leaf if leaf in items and _SYMBOL_RE.match(text) else None
            if best is not None:
                refs.append(self._ref(span, kind, items[best]))
        if not refs and _SYMBOL_RE.match(text):
            key = self._symbol_key(text)
            found = self._symbols[key] if key is not None else []
            if key is not None and len(found) == 1:
                display, line, end = found[0]
                refs.append(Reference(span, "symbol", key.rsplit(".", 1)[-1], display, line, end))
        if not refs and (text in self._abs_by_display or self._repo_file(text) is not None):
            refs.append(Reference(span, "path", text, text, None))
        return refs

    def _symbol_key(self, text: str) -> str | None:
        """The index name a symbol span is looked up under: `Class.name` when the span is
        dotted and a class has that member, else the bare name when anything has it."""
        dotted = text.removesuffix("()").split(".")
        qualified = ".".join(dotted[-2:])
        if len(dotted) > 1 and self._symbols.get(qualified):
            return qualified
        return dotted[-1] if self._symbols.get(dotted[-1]) else None

    def named_as(self, ref: Reference) -> str:
        """What tells the code `ref` names from other code of its kind: its identity, or for
        a function or class the index name its span was looked up under, so that
        `Ledger.remove` and a `remove` it falls back to are two names."""
        if ref.kind != "symbol":
            return ref.identity
        return self._symbol_key(self.strip_program(ref.span)[0]) or ref.identity

    def has(self, kind: str, name: str, display: str) -> bool:
        """Whether `display` still declares the surface identity, or defines the function or
        class, that `named_as` calls `name`."""
        if kind == "symbol":
            return any(where[0] == display for where in self._symbols.get(name, ()))
        item = self.surfaces.get(kind, {}).get(name)
        return item is not None and item.display == display

    def _repo_file(self, text: str) -> Path | None:
        """A repository file named by its repo-relative path, inside a source root or not."""
        if not text or text.startswith(("/", "..")) or any(c in text for c in " *?<>|\"'"):
            return None
        candidate = self._repo_root / text
        if self._tracked is not None:
            return candidate if text in self._tracked else None
        try:
            return candidate if candidate.is_file() else None
        except OSError:
            return None

    @staticmethod
    def _ref(span: str, kind: str, item: SurfaceItem) -> Reference:
        return Reference(span, kind, item.identity, item.display or "", item.line, item.line)

    def in_repository(self, display: str) -> bool:
        """Whether `display` is spelled from the repository root, as a change's paths are. A
        walked file in a source root outside the repository is spelled from that root."""
        path = self._abs_by_display.get(display)
        return path is None or path == self._repo_root.resolve() / display

    def declared_lines(self, ref: Reference) -> tuple[int | None, int | None]:
        """The first and last line whose change is a change to what `ref` names, or
        `(None, None)` when that is its whole file.

        A function or class is its own range and a path its file. A surface identity is its
        declaring line, or the innermost Python function that holds that line, decorators
        included, because a command's options and body are what the command is. An identity
        whose extractor gives no line is its file.
        """
        if ref.kind == "path" or ref.line is None:
            return None, None
        if ref.kind == "symbol":
            return ref.line, ref.line_end or ref.line
        holding = (ref.line, ref.line)
        # An outer function comes before the ones inside it, so the last one that holds the
        # line is the innermost.
        for first, last in self._function_lines(ref.defined_at):
            if first <= ref.line <= last:
                holding = (first, last)
        return holding

    def _function_lines(self, display: str) -> list[tuple[int, int]]:
        """The first and last line of each function a Python source file defines, at any
        depth and decorators included, in `ast.walk` order; none for any other file."""
        if display not in self._functions:
            abs_path = self._abs_by_display.get(display)
            python = PurePosixPath(display).suffix in PYTHON_PROFILE.suffixes
            module = self._reader.module(abs_path) if abs_path is not None and python else None
            self._functions[display] = [
                (
                    min([node.lineno, *(d.lineno for d in node.decorator_list)]),
                    node.end_lineno or node.lineno,
                )
                for node in (module.nodes if module is not None else ())
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
        return self._functions[display]

    def changed_after(
        self, git: GitReader, doc_abs: Path, references: list[Reference], lines: LineTimes
    ) -> bool:
        """Whether a line of what `references` name was last changed after the doc's last commit.

        The lines compared are the full range of a function or class, the declaring line of a
        surface identity, and the whole file for a path.
        """
        doc_time = last_commit_time_any_repo(git, doc_abs, self._repo_root)
        if doc_time is None or doc_time.when is None:
            return False
        doc_ts = doc_time.when.timestamp()
        for ref in references:
            abs_path = self._abs_by_display.get(ref.defined_at) or self._repo_file(ref.defined_at)
            if abs_path is None:
                continue
            newest = lines.newest(abs_path, ref.line, ref.line_end)
            if newest is not None and newest > doc_ts:
                return True
        return False
