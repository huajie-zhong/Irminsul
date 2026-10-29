"""Ignore comments — suppress a hint or time finding where a doc says why.

A doc silences one check's hint and time findings, or one such finding code, with an
HTML comment:

- `<!-- irminsul:ignore code-references reason="..." -->` covers its own line, or the next
  non-blank line when the comment stands alone, and every line of a fenced block when that
  line opens one;
- `<!-- irminsul:ignore-start code-references/unknown-symbol reason="..." -->` through the matching
  `irminsul:ignore-end` covers every line between them, fenced lines included.

A comment written inside a fence is part of the example and is never read. Certain findings
cannot be silenced this way. `irminsul check` reports comments that name only certain
findings or nothing known, blocks left open or closed without a start, and comments that
suppressed nothing.
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Final

from irminsul.checks.base import Finding, FindingClass, FindingSource, Severity
from irminsul.docgraph import DocGraph
from irminsul.fences import FenceTracker

CHECK_NAME: Final = "ignore-comment"
CODE_CERTAIN_FINDING: Final = "ignore-comment/certain-finding"
CODE_UNKNOWN_CHECK: Final = "ignore-comment/unknown-check"
CODE_UNUSED: Final = "ignore-comment/unused"
CODE_UNCLOSED_BLOCK: Final = "ignore-comment/unclosed-block"
CODE_UNMATCHED_END: Final = "ignore-comment/unmatched-end"
CODE_NO_REASON: Final = "ignore-comment/no-reason"

_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_COMMENT_RE = re.compile(
    r"<!--\s*irminsul:ignore(?P<kind>-start|-end)?\s+(?P<names>[a-z0-9/,\s-]*?)"
    r'(?:\s+reason="(?P<reason>[^"]*)")?\s*-->'
)


class IgnoreCommentFilter:
    """Ignore comments must name a known hint or time finding, give a reason, and suppress something.

    Neither a check nor a pass: it works on the findings the others produced, through
    `apply_ignore_comments`, so it declares its codes and has nothing to run.
    """

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_CERTAIN_FINDING: (
            "An ignore comment names a certain finding code, or a check whose every code is "
            "certain. Certain findings cannot be silenced from a doc; fix the finding, or "
            "remove the comment."
        ),
        CODE_UNKNOWN_CHECK: (
            "An ignore comment names no known check or finding code. Correct the name, or "
            "remove the comment."
        ),
        CODE_UNUSED: (
            "An ignore comment suppressed nothing in this run, so it hides no finding and "
            "would silently hide a future one. Remove it."
        ),
        CODE_UNCLOSED_BLOCK: (
            "An `irminsul:ignore-start` comment has no matching `irminsul:ignore-end` "
            "for the same names. Close the block."
        ),
        CODE_NO_REASON: (
            'An ignore comment carries no `reason="..."`. The reason is the whole '
            "reviewable record of why a finding was judged wrong here, so a comment "
            "without one silences a check and explains nothing. Add the reason, or fix "
            "what the finding reports."
        ),
        CODE_UNMATCHED_END: (
            "An `irminsul:ignore-end` comment has no open `irminsul:ignore-start` for the "
            "same names. Remove it or add the start."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_CERTAIN_FINDING: FindingClass.certain,
        CODE_UNKNOWN_CHECK: FindingClass.certain,
        CODE_UNUSED: FindingClass.certain,
        CODE_UNCLOSED_BLOCK: FindingClass.certain,
        CODE_UNMATCHED_END: FindingClass.certain,
        CODE_NO_REASON: FindingClass.certain,
    }


@dataclass
class _Comment:
    path: Path
    doc_id: str | None
    line: int
    names: tuple[str, ...]
    reason: str = ""
    lines: set[int] = field(default_factory=set)
    used: bool = False

    def covers(self, finding: Finding) -> bool:
        return (
            finding.path == self.path
            and finding.line in self.lines
            and (finding.check in self.names or finding.code in self.names)
        )


def apply_ignore_comments(
    findings: list[Finding], graph: DocGraph, *, ran: Collection[str] | None = None
) -> list[Finding]:
    """`findings` without the suppressed ones.

    With `ran`, the names of the checks whose findings were passed, the result also
    reports misused comments: one naming a certain code or an all-certain check, one
    naming nothing known, an unbalanced block, and one for a check that ran but
    suppressed nothing.
    """
    from irminsul.checks.pipeline import class_of, finding_sources

    comments, problems = _collect(graph)
    kept: list[Finding] = []
    for finding in findings:
        covering = (
            [c for c in comments if c.covers(finding)]
            if class_of(finding.code) not in (None, FindingClass.certain)
            else []
        )
        for comment in covering:
            comment.used = True
        if not covering:
            kept.append(finding)
    if ran is None:
        return kept

    known_checks = finding_sources()
    for comment in comments:
        if not comment.reason:
            problems.append(
                _finding(
                    comment,
                    CODE_NO_REASON,
                    f"ignore comment for {', '.join(comment.names)} gives no reason",
                )
            )
        known: list[str] = []
        for name in comment.names:
            check = known_checks.get(name.split("/", 1)[0])
            if check is None or ("/" in name and name not in check.classes):
                problems.append(
                    _finding(
                        comment, CODE_UNKNOWN_CHECK, f"'{name}' is not a check or finding code"
                    )
                )
                continue
            known.append(name)
            classes = [check.classes[name]] if "/" in name else list(check.classes.values())
            if all(c is FindingClass.certain for c in classes):
                problems.append(
                    _finding(
                        comment,
                        CODE_CERTAIN_FINDING,
                        f"'{name}' reports only certain findings, which cannot be ignored",
                    )
                )
        if (
            known
            and not comment.used
            and all(n.split("/", 1)[0] in ran for n in known)
            and not all(_time_only(known_checks, n) for n in known)
        ):
            problems.append(
                _finding(
                    comment,
                    CODE_UNUSED,
                    f"ignore comment for {', '.join(known)} suppressed nothing",
                )
            )
    return kept + problems


def _time_only(checks: dict[str, type[FindingSource]], name: str) -> bool:
    """Whether every finding a name can suppress comes from elapsed time, which may be absent
    from any one run, so a comment for it cannot be called unused."""
    check = checks[name.split("/", 1)[0]]
    classes = [check.classes[name]] if "/" in name else list(check.classes.values())
    suppressible = [c for c in classes if c is not FindingClass.certain]
    return bool(suppressible) and all(c is FindingClass.time for c in suppressible)


@dataclass(frozen=True)
class _Scanned:
    comments: list[_Comment]
    problems: list[Finding]
    coverable: dict[Path, frozenset[int]]


_collect_cache: dict[int, _Scanned] = {}


def _scanned(graph: DocGraph) -> _Scanned:
    """`_scan_all` for this graph, scanned once.

    A command that runs checks one at a time, such as `irminsul context`, comes here once
    per enabled check, and a scan reads every doc body and every guidance file.
    """
    key = id(graph)
    cached = _collect_cache.get(key)
    if cached is None:
        cached = _scan_all(graph)
        _collect_cache[key] = cached
        # Keyed by identity, so the entry has to die with the graph: `id()` is reused
        # once an object is collected, and a stale entry would answer for a later graph.
        weakref.finalize(graph, _collect_cache.pop, key, None)
    return cached


def coverable_lines(graph: DocGraph) -> Mapping[Path, frozenset[int]]:
    """The lines of each file an ignore comment can cover: the body lines of every doc and
    every line of each guidance file outside the graph, fenced lines included. A finding of
    a code that answers on its line has to sit on one of them."""
    return _scanned(graph).coverable


def _collect(graph: DocGraph) -> tuple[list[_Comment], list[Finding]]:
    """The comments and malformed markers of this graph, handed out fresh each call.

    The callers mutate what they get back: `_Comment.used` is set when a comment
    suppresses something, and `problems` is appended to. So the cache holds the scan and
    each call gets its own copies: a comment's `used` flag starts false on every call,
    and one pass never sees what another suppressed.
    """
    cached = _scanned(graph)
    comments, problems = cached.comments, cached.problems
    fresh = [
        _Comment(
            path=comment.path,
            doc_id=comment.doc_id,
            line=comment.line,
            names=comment.names,
            reason=comment.reason,
            lines=set(comment.lines),
        )
        for comment in comments
    ]
    return fresh, list(problems)


def _scan_all(graph: DocGraph) -> _Scanned:
    """Comments in every doc and in the guidance files outside the graph, such as the README."""
    comments: list[_Comment] = []
    problems: list[Finding] = []
    coverable: dict[Path, frozenset[int]] = {}

    def scan(path: Path, doc_id: str | None, numbered: list[tuple[int, str]]) -> None:
        lines: set[int] = set()
        _scan(path, doc_id, numbered, comments, problems, lines)
        coverable[path] = frozenset(lines)

    for node in graph.nodes.values():
        numbered = [(node.file_line(n), line) for n, line in enumerate(node.body.splitlines(), 1)]
        scan(node.path, node.id, numbered)
    for guidance in graph.guidance_files:
        if Path(guidance.display) in graph.by_path or guidance.text is None:
            continue
        scan(Path(guidance.display), None, list(enumerate(guidance.text.splitlines(), 1)))
    return _Scanned(comments, problems, coverable)


def _scan(
    path: Path,
    doc_id: str | None,
    numbered: list[tuple[int, str]],
    comments: list[_Comment],
    problems: list[Finding],
    coverable: set[int],
) -> None:
    """Read the comments of one file into `comments`, and every line a comment could cover
    into `coverable`.

    A fenced line is covered by the standalone comment whose next non-blank line opens the
    fence, or by an open block, and never holds a comment of its own: a comment in an
    example is part of the example.
    """
    open_blocks: dict[tuple[str, ...], _Comment] = {}
    pending: _Comment | None = None
    above_fence: _Comment | None = None
    # A toggle on any three backticks would read a four-backtick example that quotes a fenced
    # block as closing early, so an ignore comment in the example would become a live one.
    fence = FenceTracker()
    for file_line, line in numbered:
        reading = fence.classify(line)
        if reading != "outside":
            if reading == "marker" and fence.inside:
                above_fence, pending = pending, None
            for comment in (above_fence, *open_blocks.values()):
                if comment is not None:
                    comment.lines.add(file_line)
            coverable.add(file_line)
            if not fence.inside:
                above_fence = None
            continue
        coverable.add(file_line)
        if pending is not None and line.strip():
            pending.lines.add(file_line)
            pending = None
        for block in open_blocks.values():
            block.lines.add(file_line)
        prose = _INLINE_CODE_RE.sub("", line)
        for match in _COMMENT_RE.finditer(prose):
            names = tuple(n for n in re.split(r"[,\s]+", match.group("names")) if n)
            if not names:
                continue
            reason = (match.group("reason") or "").strip()
            comment = _Comment(path, doc_id, file_line, names, reason, {file_line})
            kind = match.group("kind")
            if kind == "-start":
                open_blocks[names] = comment
                comments.append(comment)
            elif kind == "-end":
                if open_blocks.pop(names, None) is None:
                    problems.append(
                        _finding(
                            comment, CODE_UNMATCHED_END, "ignore-end without an open ignore-start"
                        )
                    )
            else:
                comments.append(comment)
                if not _COMMENT_RE.sub("", prose).strip():
                    pending = comment
    for block in open_blocks.values():
        comments.remove(block)
        problems.append(
            _finding(block, CODE_UNCLOSED_BLOCK, "ignore-start without a matching ignore-end")
        )


def _finding(comment: _Comment, code: str, message: str) -> Finding:
    return Finding(
        check=CHECK_NAME,
        code=code,
        severity=Severity.warning,
        message=message,
        path=comment.path,
        doc_id=comment.doc_id,
        line=comment.line,
        suggestion=IgnoreCommentFilter.explanations[code].split(". ", 1)[-1],
    )
