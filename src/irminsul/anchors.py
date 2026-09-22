"""Anchored prose claims.

A paragraph can pin itself to a specific code symbol with an inline marker:

    <!-- anchor: src/irminsul/cli.py#check @sha256:1a2b3c -->

`file#symbol` is hand-written; the `@<algo>:<hash>` pin is written and refreshed by
the re-pin command, never by hand. In a Python file the hash is taken over the
**AST-normalized** body of the symbol (`ast.unparse`), so formatting and comment churn do
not trip it — only a real change to the code the claim describes does. In any other text
file the symbol resolves when its name appears as a whole token, and the hash is taken
over the indented block starting at its first occurrence, with whitespace normalized. A
marker inside a code span is an example, not an anchor.

This module is pure parsing/resolution/hashing; the check and the CLI command build
on it.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

ANCHOR_RE = re.compile(
    r"<!--\s*anchor:\s*(?P<path>[^\s#@]+)(?:#(?P<symbol>[^\s@]+))?"
    r"(?:\s+@(?P<algo>[a-z0-9]+):(?P<hash>[0-9a-f]+))?\s*-->"
)
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1")
_BLOCK_LINE_LIMIT = 200
_HASH_LEN = 12
_ALGO = "sha256"


@dataclass(frozen=True)
class Anchor:
    line: int
    raw: str
    path: str
    symbol: str | None
    pinned: str | None  # the hash digest, or None when unpinned


@dataclass(frozen=True)
class Resolution:
    status: str  # "ok" | "missing_file" | "missing_symbol" | "unreadable"
    current: str | None = None


def parse_anchors(body: str) -> list[Anchor]:
    """Find anchor markers in a doc body, skipping fenced code blocks."""
    anchors: list[Anchor] = []
    in_fence = False
    for lineno, line in enumerate(body.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in ANCHOR_RE.finditer(_mask_code_spans(line)):
            anchors.append(
                Anchor(
                    line=lineno,
                    raw=match.group(0),
                    path=match.group("path"),
                    symbol=match.group("symbol"),
                    pinned=match.group("hash"),
                )
            )
    return anchors


def _find_symbol(tree: ast.Module, symbol: str) -> ast.AST | None:
    """Resolve a top-level name or a dotted `Class.method`."""
    parts = symbol.split(".")
    scope: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for part in parts:
        node = next(
            (
                child
                for child in scope
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                and child.name == part
            ),
            None,
        )
        if node is None:
            return None
        scope = node.body if isinstance(node, ast.ClassDef) else []
    return node


def _hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:_HASH_LEN]


def resolve(repo_root: Path, anchor: Anchor) -> Resolution:
    """Resolve an anchor's target and compute its current normalized hash."""
    target = repo_root / anchor.path
    if not target.is_file():
        return Resolution("missing_file")
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return Resolution("unreadable")

    if target.suffix != ".py":
        return _resolve_text(text, anchor.symbol)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return Resolution("unreadable")

    if anchor.symbol is None:
        # AST-normalize even file-level anchors so formatting/comment churn does
        # not trip them.
        return Resolution("ok", _hash(ast.unparse(tree)))
    node = _find_symbol(tree, anchor.symbol)
    if node is None:
        return Resolution("missing_symbol")
    return Resolution("ok", _hash(ast.unparse(node)))


def _resolve_text(text: str, symbol: str | None) -> Resolution:
    """Resolve an anchor into a file of any language by whole-token occurrence."""
    if symbol is None:
        return Resolution("ok", _hash(_normalize_whitespace(text)))
    lines = text.splitlines()
    parts = symbol.split(".")
    if not all(_token_pattern(part).search(text) for part in parts):
        return Resolution("missing_symbol")
    after = 0
    if len(parts) > 1:
        parent = _token_pattern(parts[-2])
        after = next((i for i, line in enumerate(lines) if parent.search(line)), 0)
    start = definition_line(lines, parts[-1], after)
    if start is None:
        return Resolution("missing_symbol")
    return Resolution("ok", _hash(_normalize_whitespace("\n".join(text_block(lines, start)))))


_DEFINITION_KEYWORDS = (
    r"\b(?:def|class|function|func|fn|const|let|var|interface|type|struct|enum|trait)\s+"
)
_COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", ";")


def defines(line: str, name: str) -> bool:
    """Whether `line` defines `name`: a definition keyword before it, or an assignment."""
    escaped = re.escape(name)
    return (
        re.search(rf"{_DEFINITION_KEYWORDS}(?:\w+\s+)?{escaped}(?![\w$])", line) is not None
        or re.match(rf"^\s*(?:export\s+)?{escaped}\s*(?::|=(?!=))", line) is not None
    )


def definition_line(lines: list[str], name: str, after: int = 0) -> int | None:
    """The index of the line that defines `name` at or after `after`, else of its first
    mention outside a comment."""
    token = _token_pattern(name)
    mention: int | None = None
    for index in range(after, len(lines)):
        line = lines[index]
        if not token.search(line) or line.lstrip().startswith(_COMMENT_PREFIXES):
            continue
        if defines(line, name):
            return index
        if mention is None:
            mention = index
    return mention


def text_block(lines: list[str], start: int) -> list[str]:
    """The line at `start`, the decorator lines directly above it, and the lines indented
    under it: a definition's text in any language that indents its body."""
    first = start
    indent = _indent(lines[start])
    while (
        first > 0
        and lines[first - 1].strip().startswith("@")
        and _indent(lines[first - 1]) == indent
    ):
        first -= 1
    return lines[first:start] + _block(lines, start)


def _block(lines: list[str], start: int) -> list[str]:
    """The line at `start` and the lines indented deeper than it, plus a closing line
    at its own indentation, such as a brace."""
    indent = _indent(lines[start])
    block = [lines[start]]
    for offset, line in enumerate(lines[start + 1 : start + _BLOCK_LINE_LIMIT]):
        if not line.strip():
            block.append(line)
            continue
        if offset == 0 and line.strip() == "{":
            block.append(line)
            continue
        if _indent(line) > indent:
            block.append(line)
            continue
        if line.strip() in ("}", "};", "})", "end", "]", ")"):
            block.append(line)
        break
    return block


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _token_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _mask_code_spans(line: str) -> str:
    """The line with every inline code span blanked, keeping positions."""
    return _CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)


def _format_marker(anchor: Anchor, digest: str) -> str:
    target = anchor.path if anchor.symbol is None else f"{anchor.path}#{anchor.symbol}"
    return f"<!-- anchor: {target} @{_ALGO}:{digest} -->"


def repin_text(repo_root: Path, body: str) -> tuple[str, int]:
    """Rewrite every resolvable anchor in `body` with its current hash.

    Returns (new_body, number_of_markers_updated). Anchors whose target is missing
    are left untouched so the check still reports them.
    """
    updated = 0
    out_lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue

        masked = _mask_code_spans(line)

        def replace(match: re.Match[str], masked: str = masked) -> str:
            nonlocal updated
            if masked[match.start()] != "<":
                return match.group(0)
            anchor = Anchor(
                line=0,
                raw=match.group(0),
                path=match.group("path"),
                symbol=match.group("symbol"),
                pinned=match.group("hash"),
            )
            resolution = resolve(repo_root, anchor)
            if resolution.status != "ok" or resolution.current is None:
                return match.group(0)
            new_marker = _format_marker(anchor, resolution.current)
            if new_marker != match.group(0):
                updated += 1
            return new_marker

        out_lines.append(ANCHOR_RE.sub(replace, line))

    trailing_newline = "\n" if body.endswith("\n") else ""
    return "\n".join(out_lines) + trailing_newline, updated
