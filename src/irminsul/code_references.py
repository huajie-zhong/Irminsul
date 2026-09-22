"""Resolve names written in docs to where they are defined in code.

Shared by the review queue, which pairs a sentence with the code it names, and by the
`code-references` check, which reports a name that resolves to nothing.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from irminsul.checks.code_spans import mention_regex
from irminsul.checks.globs import walk_configured_source_files
from irminsul.config import IrminsulConfig
from irminsul.git.blame import LineTimes
from irminsul.git.mtime import last_commit_time_any_repo
from irminsul.inventory import SurfaceItem, available_kinds, get_extractor, kind_capabilities
from irminsul.inventory.programs import program_names

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
    def __init__(self, repo_root: Path, config: IrminsulConfig) -> None:
        self._repo_root = repo_root
        files = walk_configured_source_files(repo_root, config).files
        self._abs_by_display = {display: abs_path for abs_path, display in files}
        self._command_blocks: dict[str, str] | None = None
        self._command_flags: dict[str, frozenset[str]] | None = None
        self._source_tokens: set[str] | None = None
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
            extractor = get_extractor(kind, config)
            if extractor is None:
                continue
            items = extractor.extract(files, config)
            if items:
                self.surfaces[kind] = {item.identity: item for item in items}
        self._symbols = self._symbol_index(files)
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
    def _symbol_index(files: list[tuple[Path, str]]) -> dict[str, list[tuple[str, int, int]]]:
        """Python definitions by bare name and by `Class.name`."""
        index: dict[str, list[tuple[str, int, int]]] = {}
        for abs_path, display in files:
            if PurePosixPath(display).suffix != ".py":
                continue
            try:
                tree = ast.parse(abs_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
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
                try:
                    tokens.update(_IDENTIFIER_RE.findall(abs_path.read_text(encoding="utf-8")))
                except (OSError, UnicodeDecodeError):
                    continue
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
                    try:
                        text = abs_path.read_text(encoding="utf-8") if abs_path else ""
                    except (OSError, UnicodeDecodeError):
                        text = ""
                    lines_by_file[item.display] = text.splitlines()
                lines = lines_by_file[item.display]
                if 0 < item.line <= len(lines):
                    blocks[identity] = "\n".join(text_block(lines, item.line - 1))
        self._command_blocks = blocks
        return blocks

    def command_flags(self) -> dict[str, frozenset[str]]:
        """The long options each command's definition text declares."""
        if self._command_flags is None:
            self._command_flags = {
                name: frozenset(_FLAG_RE.findall(text))
                for name, text in self.command_blocks().items()
            }
        return self._command_flags

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
                leaf = text.rsplit(".", 1)[-1]
                best = leaf if leaf in items and _SYMBOL_RE.match(text) else None
            if best is not None:
                refs.append(self._ref(span, kind, items[best]))
        if not refs and _SYMBOL_RE.match(text):
            dotted = text.removesuffix("()").split(".")
            qualified = ".".join(dotted[-2:])
            name = dotted[-1]
            found = self._symbols.get(qualified) if len(dotted) > 1 else None
            if not found:
                found = self._symbols.get(name)
            if found and len(found) == 1:
                display, line, end = found[0]
                refs.append(Reference(span, "symbol", name, display, line, end))
        if not refs and (text in self._abs_by_display or self._repo_file(text) is not None):
            refs.append(Reference(span, "path", text, text, None))
        return refs

    def _repo_file(self, text: str) -> Path | None:
        """A repository file named by its repo-relative path, inside a source root or not."""
        if not text or text.startswith(("/", "..")) or any(c in text for c in " *?<>|\"'"):
            return None
        candidate = self._repo_root / text
        try:
            return candidate if candidate.is_file() else None
        except OSError:
            return None

    @staticmethod
    def _ref(span: str, kind: str, item: SurfaceItem) -> Reference:
        return Reference(span, kind, item.identity, item.display or "", item.line, item.line)

    def changed_after(self, doc_abs: Path, references: list[Reference], lines: LineTimes) -> bool:
        doc_time = last_commit_time_any_repo(doc_abs, self._repo_root)
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
