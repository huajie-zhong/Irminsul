"""Anchored prose claims (RFC 0024).

A paragraph can pin itself to a specific code symbol with an inline marker:

    <!-- anchor: src/irminsul/cli.py#check @sha256:1a2b3c -->

`file#symbol` is hand-written; the `@<algo>:<hash>` pin is written and refreshed by
the re-pin command, never by hand. The hash is taken over the **AST-normalized**
body of the symbol (`ast.unparse`), so formatting and comment churn do not trip it —
only a real change to the code the claim describes does.

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
        for match in ANCHOR_RE.finditer(line):
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
    except OSError:
        return Resolution("unreadable")

    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Non-Python (or genuinely broken) source: a file-level anchor still pins
        # to the raw text; a symbol anchor cannot be resolved.
        if anchor.symbol is None:
            return Resolution("ok", _hash(text))
        return Resolution("unreadable")

    if anchor.symbol is None:
        # AST-normalize even file-level anchors so formatting/comment churn does
        # not trip them.
        return Resolution("ok", _hash(ast.unparse(tree)))
    node = _find_symbol(tree, anchor.symbol)
    if node is None:
        return Resolution("missing_symbol")
    return Resolution("ok", _hash(ast.unparse(node)))


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

        def replace(match: re.Match[str]) -> str:
            nonlocal updated
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
