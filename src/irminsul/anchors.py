"""Anchored prose claims.

A paragraph can pin itself to a specific code symbol with an inline marker:

    <!-- anchor: src/irminsul/cli.py#check @sha256:1a2b3c -->

`file#symbol` is hand-written; the `@<algo>:<hash>` pin is written and refreshed by
the re-pin command, never by hand. In a file whose language has a reader
(`irminsul.languages`) the hash is taken over the canonical text that reader gives for the
symbol's definition. For Python that is its **syntax tree** — a function or class with its
docstring, or the whole assignment statement that binds a constant — written out as node
types and fields, without positions. Formatting and comment churn do not trip it, only a
real change to the code the claim describes does, and every Python version that parses the
code to the same tree gives the same hash. For a language tree-sitter reads it is the
definition's tree as the grammar gives it, without comments or layout. A file no reader
reads is hashed whole as text with its whitespace collapsed, and a part of one is found by
the finders of `irminsul.parts`: a heading's section in Markdown, a key in TOML, YAML or
JSON, and the lines between two `irminsul:part` markers in any file. Nothing searches a
text for a name. A marker inside a code span or a fenced block is an example, not an
anchor.

This module is parsing, resolution and hashing, which the check and the CLI command build
on, and the two readings of every pin in a doc that act on them: the re-pin, which writes,
and the stale listing, which writes nothing.
"""

from __future__ import annotations

import hashlib
import re
import shlex
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from irminsul.fences import FenceTracker, mask_code_spans
from irminsul.frontmatter import Claim
from irminsul.frontmatter_edit import set_claim_pins, strip_claim_pins
from irminsul.parts import find_part, split_part

if TYPE_CHECKING:
    from irminsul.checks.base import Finding
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.inventory.base import SourceReader
    from irminsul.languages.reader import CodeReading

ANCHOR_RE = re.compile(
    r"<!--\s*anchor:\s*(?P<path>[^\s#@]+)(?:#(?P<symbol>[^\s@]+))?"
    r"(?:\s+@(?P<algo>[a-z0-9]+):(?P<hash>[0-9a-f]+))?\s*-->"
)
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
    status: str  # "ok" | "missing_file" | "missing_symbol" | "unreadable" | "unsupported"
    """`unsupported`: the anchor names a part of a file whose type has no finder, and no
    marker in the file names it."""
    current: str | None = None
    known: tuple[str, ...] = ()
    """The names the file's finder knows, when the part an anchor names is not one of them."""
    why: str | None = None
    """What kept a name the file holds from resolving, such as two headings that share it."""


def parse_anchors(body: str) -> list[Anchor]:
    """Find anchor markers in a doc body, skipping fenced code blocks."""
    anchors: list[Anchor] = []
    fence = FenceTracker()
    for lineno, line in enumerate(body.splitlines(), start=1):
        if fence.consume(line):
            continue
        for match in ANCHOR_RE.finditer(mask_code_spans(line)):
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


_PLAIN_WORD_RE = re.compile(r"[\w@%+=:,./-][\w@%+=:,./#-]*")


def shell_word(word: str) -> str:
    """`word` as a shell reads it back whole: itself where nothing in it is special, a `#`
    after its first character included, and quoted otherwise, as a key written
    `tool."a.b"` or a path with a space must be. The command a finding suggests is built
    of these, so it runs as printed and reads as it always did where nothing needs quoting."""
    return word if _PLAIN_WORD_RE.fullmatch(word) else shlex.quote(word)


def _hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:_HASH_LEN]


def resolve(repo_root: Path, anchor: Anchor, reader: SourceReader | None = None) -> Resolution:
    """Resolve an anchor's target and compute its current normalized hash.

    `reader` is the snapshot to read the target from; a caller with a graph passes
    `graph.source`, so a file is parsed once however many anchors name it. A whole file is
    hashed over the canonical text its language's reader gives, or as text where no reader
    reads it. A part is found by the finders of `irminsul.parts` and by nothing else: a
    part the file's finder does not know is missing when the whole file parsed and
    unreadable when part of it did not, since the name may be in that part, and a part of a
    file whose type has no finder and that holds no marker for it is unsupported."""
    from irminsul.inventory.base import SourceReader

    reader = reader or SourceReader()
    target = repo_root / anchor.path
    if not target.is_file():
        return Resolution("missing_file")
    text = reader.text(target)
    if text is None:
        return Resolution("unreadable")

    reading = reader.reading(target)
    if anchor.symbol is None:
        whole = _whole(target, text, reading)
        return Resolution("unreadable") if whole is None else Resolution("ok", _hash(whole))
    part = find_part(
        target.suffix,
        text,
        anchor.symbol,
        reading,
        lambda region: _whole(target, region, reader.read_text(target, region)),
    )
    if part.status == "ok" and part.text is not None:
        return Resolution("ok", _hash(part.text))
    status = "missing_symbol" if part.status in ("ok", "missing") else part.status
    return Resolution(status, known=part.known, why=part.why)


def _whole(target: Path, text: str, reading: CodeReading | None) -> str | None:
    """The text a pin hashes for the whole of `text`, a file of `target`'s type or a region
    of one: what its language's reader gives, which is None for a text Python cannot parse,
    and where no reader reads the type, the text with its whitespace collapsed, a doc
    without its pins."""
    if reading is not None:
        return reading.canonical()
    return _normalize_whitespace(without_pins(text) if target.suffix == ".md" else text)


def without_pins(text: str) -> str:
    """`text` with its pins left out, the one reading that compares a doc's words.

    An anchor marker reads as `anchor <target>`, without its `@algo:hash`, and each claim's
    `pinned` map leaves the frontmatter. A re-pin writes only pins, so it changes nothing
    this reading compares.
    """
    unpinned = ANCHOR_RE.sub(lambda match: f"anchor {match['path']}#{match['symbol'] or ''}", text)
    return strip_claim_pins(unpinned)


def resolve_evidence(
    target: Path, part: str | None, reader: SourceReader | None = None
) -> Resolution:
    """What a claim's evidence entry resolves to: the whole file `target`, or the part of
    it the entry names, found as an anchor's part is."""
    anchor = Anchor(line=0, raw="", path=target.name, symbol=part, pinned=None)
    return resolve(target.parent, anchor, reader)


def file_pin(
    target: Path, reader: SourceReader | None = None, part: str | None = None
) -> str | None:
    """`<algo>:<hash>` of a whole file, or of the part `part` of it, normalized as an
    anchor's hash is, or None when it is not a readable file or holds no such part.

    A claim pins its evidence with this, so a formatting-only commit to the evidence does
    not re-ask a claim someone already re-read, and one that names a part is not re-asked
    by a change elsewhere in the file. A doc is hashed without its pins, as `resolve`
    hashes any doc a file-level anchor names, so a re-pin of the doc, which rewrites only
    pins, does not re-ask the claims that cite it.
    """
    resolution = resolve_evidence(target, part, reader)
    return f"{_ALGO}:{resolution.current}" if resolution.status == "ok" else None


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


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _format_marker(anchor: Anchor, digest: str) -> str:
    return f"<!-- anchor: {anchor.target} @{_ALGO}:{digest} -->"


@dataclass(frozen=True)
class RepinScope:
    """The pins one re-pin may move. With no selector, every pin in the doc.

    `claims` and `anchors` select by claim id and by anchor target. `evidence` narrows the
    selected claims to the evidence entries it names, for every selected claim alike: an
    entry by its spelling, `path#part` included, and every entry of a file by its bare path.
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
    files = {split_part(entry)[0] for entry in cited}

    def known(names: set[str]) -> str:
        return ", ".join(sorted(names)) or "none"

    for claim_id in sorted(scope.claims - claim_ids):
        out.append(f"--claim: no claim with id {claim_id} (the doc has: {known(claim_ids)})")
    for target in sorted(scope.anchors - targets):
        out.append(f"--anchor: no anchor {target} (the doc has: {known(targets)})")
    for path in sorted(scope.evidence - cited - files):
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

        masked = mask_code_spans(line)

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
    """Pin every evidence entry of every claim in one doc to its current hash, or only the
    claims `only` names, and within them only the evidence `only_evidence` names: an entry
    by its spelling, or every entry of a file by the file's bare path.

    Returns (new_text, a `claim <id>: <evidence>` label for each pin written or dropped).
    A pin is keyed by the entry as the claim writes it, and hashes the part the entry names
    or the whole file. `locate` resolves an entry's path to a file. An entry whose file is
    not readable, or whose part does not resolve, keeps the pin it had, if any: the check
    reports it on its own. A pin on a spelling the claim no longer cites is dropped, since
    nothing reads it; with `only_evidence`, the pin of every other entry is left as it is.
    """
    written: list[str] = []
    pins: dict[str, dict[str, str]] = {}
    hashed: dict[tuple[Path, str | None], str | None] = {}
    for claim in claims:
        if only is not None and claim.id not in only:
            continue
        claim_pins: dict[str, str] = {}
        for evidence in claim.evidence:
            path, part = split_part(evidence)
            if only_evidence and evidence not in only_evidence and path not in only_evidence:
                continue
            target = locate(path)
            if target is not None and (target, part) not in hashed:
                hashed[target, part] = file_pin(target, part=part)
            fresh = hashed[target, part] if target is not None else None
            if fresh is not None:
                claim_pins[evidence] = fresh
            elif evidence in claim.pinned:
                claim_pins[evidence] = claim.pinned[evidence]
        if only_evidence:
            kept = {entry: claim.pinned[entry] for entry in claim.evidence if entry in claim.pinned}
            claim_pins = {**kept, **claim_pins}
        for path in [*claim_pins, *(path for path in claim.pinned if path not in claim_pins)]:
            if claim_pins.get(path) != claim.pinned.get(path):
                dropped = " (dropped)" if path not in claim_pins else ""
                written.append(f"claim {claim.id}: {path}{dropped}")
        pins[claim.id] = claim_pins
    return (set_claim_pins(text, pins) if written else text), written


ANCHOR_KIND = "anchor"
EVIDENCE_KIND = "claim-evidence"
#: How `claim-anchor/pinned-drift` and `claim-provenance/evidence-drift` spell what they are
#: about, read back so a stale pin can say whether a check reports it. Neither finding carries
#: its target, claim or evidence as data, and a quoted name ends at the first `'`, so a pin
#: whose path or claim id holds one is reported by nothing (`drift-findings-carry-no-subject`).
_PINNED_DRIFT_RE = re.compile(r"^'(?P<target>[^']+)' changed since this claim was pinned")
_EVIDENCE_DRIFT_RE = re.compile(
    r"^claim '(?P<claim>[^']+)' cites evidence changed after the doc[^:]*: (?P<named>.+)$"
)
_QUOTED_RE = re.compile(r"'([^']+)'")


@dataclass(frozen=True)
class StalePin:
    """A pin that no longer matches what it pins: an anchor whose target resolves and hashes
    differently, or a claim's evidence file that does."""

    doc: str
    line: int
    kind: str
    """`anchor` or `claim-evidence`."""
    target: str
    """`path#symbol` for an anchor, the evidence path as the claim spells it for a claim."""
    claim: str | None
    pinned: str
    current: str
    reported_by: str | None = None
    """The code of the finding that already asks about this pin, or None when none does."""

    @property
    def label(self) -> str:
        """How a re-pin names the pin it moves: `anchor <target>`, `claim <id>: <evidence>`."""
        if self.claim is None:
            return f"anchor {self.target}"
        return f"claim {self.claim}: {self.target}"

    @property
    def re_pin(self) -> str:
        """The whole command that re-pins this pin, each argument shell-quoted so it runs
        as printed. `--anchor` names a target, so it also moves another
        anchor of the doc with the same `path#symbol`. `--evidence` with an entry that
        names a part moves that pin alone; with a bare path it moves every entry of that
        file, so the pins of a claim that cites a file whole and by a part move together."""
        narrow = (
            ["--anchor", self.target]
            if self.claim is None
            else ["--claim", self.claim, "--evidence", self.target]
        )
        words = ["irminsul", "anchors", "--re-pin", "--doc", self.doc, *narrow]
        return " ".join(shlex.quote(word) for word in words)

    def as_json(self) -> dict[str, object]:
        return {
            "doc": self.doc,
            "line": self.line,
            "kind": self.kind,
            "target": self.target,
            "claim": self.claim,
            "pinned": self.pinned,
            "current": self.current,
            "reported_by": self.reported_by,
            "re_pin": self.re_pin,
        }


def stale_pins(graph: DocGraph, doc: str | None = None) -> list[StalePin]:
    """Every anchor and claim evidence pin in the graph's docs, or in the one at the
    repo-relative path `doc`, whose target's current hash differs from its pin, by doc and
    line. Nothing is written.

    Each is read through `resolve` and `file_pin`, as a re-pin reads it. A target that does
    not resolve is left to the findings that report it, and a pin on a path its claim no
    longer cites is not read, as nothing else reads it. `reported_by` names the
    `claim-anchor` or `claim-provenance` finding about the same pin in a run of those checks
    over `graph`: an `evidence-drift` finding names only the evidence that changed after the
    doc, in the layers it judges, so a stale pin it does not name is reported by nothing.
    """
    from irminsul.checks.claim_anchor import ClaimAnchorCheck
    from irminsul.checks.claim_provenance import ClaimProvenanceCheck
    from irminsul.checks.globs import resolve_display_path
    from irminsul.checks.pipeline import run_check, select_checks

    repo_root, config = graph.repo_root, graph.config
    if repo_root is None or config is None:
        return []

    def locate(spelling: str) -> Path | None:
        return resolve_display_path(repo_root, config.paths.source_roots, spelling)

    hashed: dict[tuple[Path, str | None], str | None] = {}
    found: list[StalePin] = []
    for node in sorted(graph.nodes.values(), key=lambda n: n.path.as_posix()):
        if doc is not None and node.path.as_posix() != doc:
            continue
        found.extend(_stale_anchors(repo_root, node, graph.source))
        found.extend(_stale_evidence(node, locate, hashed, graph.source))
    if not found:
        return []
    # Only the checks the configuration enables, so `reported_by` names a finding `check`
    # reports. A baseline holds certain findings alone and both drift codes are hints, so no
    # baseline can hide one.
    enabled = set(select_checks(config))
    findings = [
        finding
        for check in (ClaimAnchorCheck, ClaimProvenanceCheck)
        if check.name in enabled
        for finding in run_check(check, graph)
    ]
    reported = _reported_pins(findings)
    rows = [replace(pin, reported_by=reported.get(_pin_key(pin))) for pin in found]
    return sorted(rows, key=lambda pin: (pin.doc, pin.line, pin.kind, pin.target))


def _stale_anchors(repo_root: Path, node: DocNode, reader: SourceReader) -> Iterator[StalePin]:
    for anchor in parse_anchors(node.body):
        if anchor.pinned is None:
            continue
        resolution = resolve(repo_root, anchor, reader)
        if resolution.status != "ok" or resolution.current in (None, anchor.pinned):
            continue
        match = ANCHOR_RE.match(anchor.raw)
        algo = match["algo"] if match is not None else _ALGO
        yield StalePin(
            doc=node.path.as_posix(),
            line=node.file_line(anchor.line),
            kind=ANCHOR_KIND,
            target=anchor.target,
            claim=None,
            pinned=f"{algo}:{anchor.pinned}",
            current=f"{_ALGO}:{resolution.current}",
        )


def _stale_evidence(
    node: DocNode,
    locate: Callable[[str], Path | None],
    hashed: dict[tuple[Path, str | None], str | None],
    reader: SourceReader,
) -> Iterator[StalePin]:
    for claim in node.frontmatter.claims:
        for evidence in claim.evidence:
            pin = claim.pinned.get(evidence)
            path, part = split_part(evidence)
            target = locate(path) if pin is not None else None
            if pin is None or target is None:
                continue
            if (target, part) not in hashed:
                hashed[target, part] = file_pin(target, reader, part)
            current = hashed[target, part]
            if current is None or current == pin:
                continue
            yield StalePin(
                doc=node.path.as_posix(),
                line=_claim_marker_line(node, claim.id),
                kind=EVIDENCE_KIND,
                target=evidence,
                claim=claim.id,
                pinned=pin,
                current=current,
            )


def _claim_marker_line(node: DocNode, claim_id: str) -> int:
    """The file line of the first `<!-- claim:<id> -->` marker in the body, or 1 when no
    paragraph declares the claim."""
    marker = re.compile(rf"<!--\s*claim:{re.escape(claim_id)}\s*-->")
    fence = FenceTracker()
    for lineno, line in enumerate(node.body.splitlines(), start=1):
        if fence.consume(line):
            continue
        if marker.search(mask_code_spans(line)):
            return node.file_line(lineno)
    return 1


def _pin_key(pin: StalePin) -> tuple[str, ...]:
    if pin.claim is None:
        return (ANCHOR_KIND, pin.doc, str(pin.line), pin.target)
    return (EVIDENCE_KIND, pin.doc, pin.claim, pin.target)


def _reported_pins(findings: list[Finding]) -> dict[tuple[str, ...], str]:
    """The pins the drift findings among `findings` ask about, each with the finding's code:
    an anchor by its doc, line and target, a claim's evidence by its doc, claim and path."""
    from irminsul.checks.claim_anchor import CODE_PINNED_DRIFT
    from irminsul.checks.claim_provenance import CODE_EVIDENCE_DRIFT

    out: dict[tuple[str, ...], str] = {}
    for finding in findings:
        if finding.path is None:
            continue
        doc = finding.path.as_posix()
        if finding.code == CODE_PINNED_DRIFT and finding.line is not None:
            anchor = _PINNED_DRIFT_RE.match(finding.message)
            if anchor is not None:
                out[(ANCHOR_KIND, doc, str(finding.line), anchor["target"])] = finding.code
        elif finding.code == CODE_EVIDENCE_DRIFT:
            drift = _EVIDENCE_DRIFT_RE.match(finding.message)
            if drift is not None:
                for path in _QUOTED_RE.findall(drift["named"]):
                    out[(EVIDENCE_KIND, doc, drift["claim"], path)] = finding.code
    return out
