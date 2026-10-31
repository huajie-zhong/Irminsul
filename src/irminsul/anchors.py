"""Anchored prose claims.

A paragraph can pin itself to a specific code symbol with an inline marker:

    <!-- anchor: src/irminsul/cli.py#check @sha256:1a2b3c -->

`file#symbol` is hand-written; the `@<algo>:<hash>` pin is written and refreshed by
the re-pin command, never by hand. In a Python file the hash is taken over the **syntax
tree** of the symbol's definition — a function or class with its docstring, or the whole
assignment statement that binds a constant — written out by `_canonical` as node types and
fields, without positions. Formatting and comment churn do not trip it, only a real change
to the code the claim describes does, and every Python version that parses the code to the
same tree gives the same hash. In any other text
file the symbol resolves when its name appears as a whole token, and the hash is taken
over the block that defines it, with whitespace normalized: the line that defines the
name (a definition keyword or an assignment, else its first mention outside a comment),
the decorator lines above it, and the lines indented under it. A marker inside a code
span or a fenced block is an example, not an anchor.

This module is pure parsing/resolution/hashing; the check and the CLI command build
on it.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from irminsul.fences import FenceTracker
from irminsul.frontmatter import Claim
from irminsul.frontmatter_edit import set_claim_pins, strip_claim_pins

if TYPE_CHECKING:
    from irminsul.inventory.base import SourceReader

ANCHOR_RE = re.compile(
    r"<!--\s*anchor:\s*(?P<path>[^\s#@]+)(?:#(?P<symbol>[^\s@]+))?"
    r"(?:\s+@(?P<algo>[a-z0-9]+):(?P<hash>[0-9a-f]+))?\s*-->"
)
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

    @property
    def target(self) -> str:
        """`path#symbol`, or `path` for a file-level anchor: how the marker, a finding and
        `anchors --re-pin --anchor` all spell it."""
        return self.path if self.symbol is None else f"{self.path}#{self.symbol}"


@dataclass(frozen=True)
class Resolution:
    status: str  # "ok" | "missing_file" | "missing_symbol" | "unreadable"
    current: str | None = None


def parse_anchors(body: str) -> list[Anchor]:
    """Find anchor markers in a doc body, skipping fenced code blocks."""
    anchors: list[Anchor] = []
    fence = FenceTracker()
    for lineno, line in enumerate(body.splitlines(), start=1):
        if fence.consume(line):
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


@dataclass(frozen=True)
class PythonDefinition:
    symbol: str
    """The dotted path from the module to the definition, such as `Store.flush`."""
    line: int
    reachable: bool
    """Whether an anchor can name it: only classes enclose it, so `_find_symbol` descends."""


def python_definitions(tree: ast.Module, name: str) -> list[PythonDefinition]:
    """Every statement in `tree` that defines `name`, in source order, however deeply
    nested — except an assignment inside a function, which is a local variable rather
    than anything a doc would name."""
    out: list[PythonDefinition] = []
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def walk(body: list[ast.stmt], scope: list[str], reachable: bool, local: bool) -> None:
        for node in body:
            if _defines(node, name) and (isinstance(node, definitions) or not local):
                out.append(PythonDefinition(".".join([*scope, name]), node.lineno, reachable))
            if isinstance(node, ast.ClassDef):
                walk(node.body, [*scope, node.name], reachable, False)
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                walk(node.body, [*scope, node.name], False, True)
            else:
                for inner in _statement_bodies(node):
                    walk(inner, scope, False, local)

    walk(tree.body, [], True, False)
    return out


def _statement_bodies(node: ast.stmt) -> Iterator[list[ast.stmt]]:
    for field_name in ("body", "orelse", "finalbody"):
        value = getattr(node, field_name, None)
        if isinstance(value, list) and all(isinstance(item, ast.stmt) for item in value):
            yield value
    for handler in getattr(node, "handlers", []):
        yield handler.body
    for case in getattr(node, "cases", []):
        yield case.body


def _hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:_HASH_LEN]


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


def resolve(repo_root: Path, anchor: Anchor, reader: SourceReader | None = None) -> Resolution:
    """Resolve an anchor's target and compute its current normalized hash.

    `reader` is the snapshot to read the target from; a caller with a graph passes
    `graph.source`, so a file is parsed once however many anchors name it."""
    from irminsul.inventory.base import SourceReader

    reader = reader or SourceReader()
    target = repo_root / anchor.path
    if not target.is_file():
        return Resolution("missing_file")
    text = reader.text(target)
    if text is None:
        return Resolution("unreadable")

    if target.suffix != ".py":
        if target.suffix == ".md" and anchor.symbol is None:
            text = without_pins(text)
        return _resolve_text(text, anchor.symbol)
    module = reader.module(target)
    if module is None:
        return Resolution("unreadable")
    tree = module.tree

    if anchor.symbol is None:
        return Resolution("ok", _hash(_canonical(tree)))
    node = _find_symbol(tree, anchor.symbol)
    if node is None:
        return Resolution("missing_symbol")
    return Resolution("ok", _hash(_canonical(node)))


def without_pins(text: str) -> str:
    """`text` with its pins left out, the one reading that compares a doc's words.

    An anchor marker reads as `anchor <target>`, without its `@algo:hash`, and each claim's
    `pinned` map leaves the frontmatter. A re-pin writes only pins, so it changes nothing
    this reading compares.
    """
    unpinned = ANCHOR_RE.sub(lambda match: f"anchor {match['path']}#{match['symbol'] or ''}", text)
    return strip_claim_pins(unpinned)


def file_pin(target: Path, reader: SourceReader | None = None) -> str | None:
    """`<algo>:<hash>` of a whole file, normalized as a file-level anchor's hash is, or
    None when it is not a readable file.

    A claim pins its evidence with this, so a formatting-only commit to the evidence does
    not re-ask a claim someone already re-read. A doc is hashed without its pins, as
    `resolve` hashes any doc a file-level anchor names, so a re-pin of the doc, which
    rewrites only pins, does not re-ask the claims that cite it.
    """
    anchor = Anchor(line=0, raw="", path=target.name, symbol=None, pinned=None)
    resolution = resolve(target.parent, anchor, reader)
    return f"{_ALGO}:{resolution.current}" if resolution.status == "ok" else None


def _resolve_text(text: str, symbol: str | None) -> Resolution:
    """Resolve an anchor into a file of any language by whole-token occurrence.

    A dotted name is looked for after its parent's first mention.
    """
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
    at its own indentation, such as a brace. A lone `{` on the line right after `start`
    stays in the block, so a brace placed on its own line opens it."""
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
    return f"<!-- anchor: {anchor.target} @{_ALGO}:{digest} -->"


@dataclass(frozen=True)
class RepinScope:
    """The pins one re-pin may move. With no selector, every pin in the doc.

    `claims` and `anchors` select by claim id and by anchor target. `evidence` narrows the
    selected claims to the evidence files it names, for every selected claim alike.
    """

    claims: frozenset[str] = frozenset()
    evidence: frozenset[str] = frozenset()
    anchors: frozenset[str] = frozenset()

    @property
    def selective(self) -> bool:
        return bool(self.claims or self.anchors)


def unknown_selectors(body: str, claims: list[Claim], scope: RepinScope) -> list[str]:
    """What `scope` names that the doc does not hold, one message each."""
    out: list[str] = []
    claim_ids = {claim.id for claim in claims}
    targets = {anchor.target for anchor in parse_anchors(body)}
    cited = {path for claim in claims if claim.id in scope.claims for path in claim.evidence}

    def known(names: set[str]) -> str:
        return ", ".join(sorted(names)) or "none"

    for claim_id in sorted(scope.claims - claim_ids):
        out.append(f"--claim: no claim with id {claim_id} (the doc has: {known(claim_ids)})")
    for target in sorted(scope.anchors - targets):
        out.append(f"--anchor: no anchor {target} (the doc has: {known(targets)})")
    for path in sorted(scope.evidence - cited):
        out.append(f"--evidence: no selected claim cites {path} (they cite: {known(cited)})")
    return out


def repin_doc(
    repo_root: Path,
    text: str,
    claims: list[Claim],
    locate: Callable[[str], Path | None],
    scope: RepinScope,
) -> tuple[str, list[str], list[str]]:
    """Re-pin the anchors and claim evidence of one doc that `scope` allows.

    Returns (new_text, the `anchor <path#symbol>` label of each anchor moved, the
    `claim <id>: <evidence>` label of each claim pin moved), so a re-pin can say what it
    acknowledged.
    """
    anchors: list[str] = []
    pins: list[str] = []
    if scope.anchors or not scope.selective:
        text, anchors = repin_text(repo_root, text, scope.anchors or None)
    if scope.claims or not scope.selective:
        text, pins = repin_claims(text, claims, locate, scope.claims or None, scope.evidence)
    return text, anchors, pins


def repin_text(
    repo_root: Path, body: str, only: Collection[str] | None = None
) -> tuple[str, list[str]]:
    """Rewrite every resolvable anchor in `body` with its current hash, or only those
    whose target `only` names.

    Returns (new_body, an `anchor <target>` label for each marker updated). Anchors whose
    target is missing are left untouched so the check still reports them.
    """
    updated: list[str] = []
    out_lines: list[str] = []
    fence = FenceTracker()
    for line in body.splitlines():
        if fence.consume(line):
            out_lines.append(line)
            continue

        masked = _mask_code_spans(line)

        def replace(match: re.Match[str], masked: str = masked) -> str:
            if masked[match.start()] != "<":
                return match.group(0)
            anchor = Anchor(
                line=0,
                raw=match.group(0),
                path=match.group("path"),
                symbol=match.group("symbol"),
                pinned=match.group("hash"),
            )
            if only is not None and anchor.target not in only:
                return match.group(0)
            resolution = resolve(repo_root, anchor)
            if resolution.status != "ok" or resolution.current is None:
                return match.group(0)
            new_marker = _format_marker(anchor, resolution.current)
            if new_marker != match.group(0):
                updated.append(f"anchor {anchor.target}")
            return new_marker

        out_lines.append(ANCHOR_RE.sub(replace, line))

    if not updated:
        return body, updated
    trailing_newline = "\n" if body.endswith("\n") else ""
    return "\n".join(out_lines) + trailing_newline, updated


def repin_claims(
    text: str,
    claims: list[Claim],
    locate: Callable[[str], Path | None],
    only: Collection[str] | None = None,
    only_evidence: Collection[str] = (),
) -> tuple[str, list[str]]:
    """Pin every evidence file of every claim in one doc to its current hash, or only the
    claims `only` names, and within them only the evidence `only_evidence` names.

    Returns (new_text, a `claim <id>: <evidence>` label for each pin written or dropped).
    `locate` resolves an evidence spelling to a file. Evidence that is not a readable file
    keeps the pin it had, if any: the check reports a missing path on its own. A pin on a
    path the claim no longer cites is dropped, since nothing reads it; with
    `only_evidence`, every pin it does not name is left as it is.
    """
    written: list[str] = []
    pins: dict[str, dict[str, str]] = {}
    hashed: dict[Path, str | None] = {}
    for claim in claims:
        if only is not None and claim.id not in only:
            continue
        claim_pins: dict[str, str] = {}
        for evidence in claim.evidence:
            if only_evidence and evidence not in only_evidence:
                continue
            target = locate(evidence)
            if target is not None and target not in hashed:
                hashed[target] = file_pin(target)
            fresh = hashed[target] if target is not None else None
            if fresh is not None:
                claim_pins[evidence] = fresh
            elif evidence in claim.pinned:
                claim_pins[evidence] = claim.pinned[evidence]
        if only_evidence:
            claim_pins = {**claim.pinned, **claim_pins}
        for path in [*claim_pins, *(path for path in claim.pinned if path not in claim_pins)]:
            if claim_pins.get(path) != claim.pinned.get(path):
                dropped = " (dropped)" if path not in claim_pins else ""
                written.append(f"claim {claim.id}: {path}{dropped}")
        pins[claim.id] = claim_pins
    return (set_claim_pins(text, pins) if written else text), written
