"""Glossary discipline check.

Glossary enforcement is opt-in per term: a heading in
`GLOSSARY.md` may declare explicit match strings, forbidden synonyms, and case
sensitivity. A bare glossary heading is valid and has no rule to apply.
"""

from __future__ import annotations

import ast
import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Answer, Finding, FindingClass, Fix, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import Link, is_external, resolve_href, slugify
from irminsul.fences import FenceTracker
from irminsul.frontmatter_edit import split_frontmatter

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_KNOWN_METADATA_KEYS = frozenset({"match", "forbidden_synonyms", "case_sensitive"})
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)")
_HEADING_LINE_RE = re.compile(r"(?m)^#{1,6}[^\n]*$")
#: An HTML comment is not rendered prose, and two kinds of it are load-bearing:
#: `<!-- anchor: path#symbol @sha256:... -->` seals a claim, and an `irminsul:ignore`
#: comment records why a finding was judged wrong. Auto-linking a glossary term inside
#: either one corrupts it — an anchor whose path gained a markdown link stops resolving.
_HTML_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    match_terms: tuple[str, ...]
    forbidden_synonyms: tuple[str, ...]
    case_sensitive: bool
    has_metadata: bool
    line: int


@dataclass(frozen=True)
class GlossaryParseIssue:
    line: int
    message: str


@dataclass(frozen=True)
class _NodeGlossaryCache:
    node: DocNode
    masked_body: str
    glossary_anchors: frozenset[str]


def _parse_glossary_entries(
    glossary_text: str,
) -> tuple[list[GlossaryEntry], set[str], list[GlossaryParseIssue]]:
    """Parse heading-shaped glossary entries and anti-glossary bullets."""
    lines = glossary_text.splitlines()
    entries: list[GlossaryEntry] = []
    anti: set[str] = set()
    issues: list[GlossaryParseIssue] = []

    i = 0
    in_anti = False
    while i < len(lines):
        line = lines[i]
        heading_match = _HEADING_RE.match(line)
        if not heading_match:
            if in_anti:
                stripped = line.strip()
                if stripped.startswith(("-", "*", "+")):
                    anti.add(stripped.lstrip("-*+ ").strip())
            i += 1
            continue

        level = len(heading_match.group(1))
        text = heading_match.group(2).strip()
        if level == 2 and text.lower() == "anti-glossary":
            in_anti = True
            i += 1
            continue
        if level <= 2:
            in_anti = False
        if level != 2 or in_anti:
            i += 1
            continue

        entry, entry_issues = _parse_entry_metadata(text, i + 1, lines, i + 1)
        entries.append(entry)
        issues.extend(entry_issues)
        i += 1

    return entries, anti, issues


def _parse_entry_metadata(
    term: str,
    heading_line: int,
    lines: list[str],
    first_body_index: int,
) -> tuple[GlossaryEntry, list[GlossaryParseIssue]]:
    issues: list[GlossaryParseIssue] = []
    metadata: dict[str, object] = {}

    i = first_body_index
    while i < len(lines) and not lines[i].strip():
        i += 1

    has_metadata = False
    while i < len(lines):
        line = lines[i]
        if _HEADING_RE.match(line):
            break
        if not line.strip():
            if has_metadata:
                break
            i += 1
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or key not in _KNOWN_METADATA_KEYS:
            break
        has_metadata = True
        metadata[key] = _parse_metadata_value(key, value.strip(), i + 1, issues)
        i += 1

    match_terms = _metadata_string_list(metadata.get("match"), "match", heading_line, issues)
    forbidden = _metadata_string_list(
        metadata.get("forbidden_synonyms"),
        "forbidden_synonyms",
        heading_line,
        issues,
    )
    case_sensitive = _metadata_bool(
        metadata.get("case_sensitive"),
        default=True,
        key="case_sensitive",
        line=heading_line,
        issues=issues,
    )

    if has_metadata and not match_terms:
        match_terms = (term,)

    return (
        GlossaryEntry(
            term=term,
            match_terms=match_terms,
            forbidden_synonyms=forbidden,
            case_sensitive=case_sensitive,
            has_metadata=has_metadata,
            line=heading_line,
        ),
        issues,
    )


def _parse_metadata_value(
    key: str,
    raw_value: str,
    line: int,
    issues: list[GlossaryParseIssue],
) -> object:
    if key == "case_sensitive":
        lowered = raw_value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        issues.append(GlossaryParseIssue(line, f"`{key}` must be true or false"))
        return None

    try:
        return ast.literal_eval(raw_value)
    except (SyntaxError, ValueError) as exc:
        issues.append(GlossaryParseIssue(line, f"`{key}` must be an inline string list: {exc}"))
        return None


def _metadata_string_list(
    value: object,
    key: str,
    line: int,
    issues: list[GlossaryParseIssue],
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        issues.append(GlossaryParseIssue(line, f"`{key}` must be a list of strings"))
        return ()
    return tuple(item for item in value if item)


def _metadata_bool(
    value: object,
    *,
    default: bool,
    key: str,
    line: int,
    issues: list[GlossaryParseIssue],
) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    issues.append(GlossaryParseIssue(line, f"`{key}` must be boolean"))
    return default


def _mask_fenced_lines(body: str) -> str:
    """Blank every fenced line, keeping each line's length so offsets still map to lines."""
    fence = FenceTracker()
    return "\n".join(" " * len(line) if fence.consume(line) else line for line in body.split("\n"))


def _masked_body(body: str) -> str:
    masked = _mask_fenced_lines(body)
    for pattern in (_INLINE_CODE_RE, _HTML_COMMENT_RE):
        masked = pattern.sub(lambda match: _blank_preserve_newlines(match.group(0)), masked)
    return masked


def _masked_for_link(body: str) -> str:
    """Mask code, headings, and existing links so auto-linking never nests.

    Headings are masked so the fix targets a prose occurrence rather than
    wrapping a section title in a link.
    """
    masked = _masked_body(body)
    for pattern in (_HEADING_LINE_RE, _LINK_RE):
        masked = pattern.sub(lambda match: _blank_preserve_newlines(match.group(0)), masked)
    return masked


def _earliest_match(
    masked: str, terms: tuple[str, ...], *, case_sensitive: bool
) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    for term in terms:
        m = _term_pattern(term, case_sensitive=case_sensitive).search(masked)
        if m is not None and (best is None or m.start() < best[0]):
            best = (m.start(), m.end())
    return best


def _autolink_apply(
    terms: tuple[str, ...], *, case_sensitive: bool, link: str
) -> Callable[[str], str]:
    """Wrap the first unlinked occurrence of any term with the glossary link.

    Idempotent: once wrapped, the term sits inside a link that masking blanks,
    so a re-run finds no bare occurrence and returns the text unchanged.
    """

    def apply(text: str) -> str:
        try:
            _raw, body = split_frontmatter(text)
        except ValueError:
            return text
        span = _earliest_match(_masked_for_link(body), terms, case_sensitive=case_sensitive)
        if span is None:
            return text
        base = len(text) - len(body)
        start, end = base + span[0], base + span[1]
        return f"{text[:start]}[{text[start:end]}]({link}){text[end:]}"

    return apply


def _blank_preserve_newlines(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _first_match_line(masked_body: str, term: str, *, case_sensitive: bool) -> int | None:
    match = _term_pattern(term, case_sensitive=case_sensitive).search(masked_body)
    if match is None:
        return None
    return masked_body[: match.start()].count("\n") + 1


def _has_match(masked_body: str, term: str, *, case_sensitive: bool) -> bool:
    return _first_match_line(masked_body, term, case_sensitive=case_sensitive) is not None


def _term_pattern(term: str, *, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags)


def _linked_glossary_anchors(node: DocNode, glossary_rel: Path) -> set[str]:
    anchors: set[str] = set()
    for link in node.links:
        anchor = _link_glossary_anchor(node, link, glossary_rel)
        if anchor is not None:
            anchors.add(anchor)
    return anchors


def _link_glossary_anchor(src_node: DocNode, link: Link, glossary_rel: Path) -> str | None:
    if link.anchor is None or is_external(link.href):
        return None
    source = src_node.path.as_posix()
    if not link.target:
        return link.anchor if source == glossary_rel.as_posix() else None
    resolved = resolve_href(source, link.target)
    if resolved is None or resolved.as_posix() != glossary_rel.as_posix():
        return None
    return link.anchor


CODE_MALFORMED_METADATA = "glossary-discipline/malformed-metadata"
CODE_FORBIDDEN_SYNONYM = "glossary-discipline/forbidden-synonym"
CODE_UNLINKED_TERM = "glossary-discipline/unlinked-term"
CODE_UNUSED_TERM = "glossary-discipline/unused-term"


class GlossaryDisciplineCheck:
    name: ClassVar[str] = "glossary-discipline"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_MALFORMED_METADATA: (
            "A glossary entry's `match`/`forbidden_synonyms`/`case_sensitive` metadata "
            "failed to parse. Fix the malformed line in GLOSSARY.md."
        ),
        CODE_FORBIDDEN_SYNONYM: (
            "A doc uses a synonym the glossary entry explicitly forbids. Use the "
            "canonical term instead."
        ),
        CODE_UNLINKED_TERM: (
            "A doc uses a glossary term with metadata but never links its first "
            "occurrence to the glossary anchor. Link the first use."
        ),
        CODE_UNUSED_TERM: (
            "A glossary entry with metadata is declared but never used or linked "
            "anywhere. Remove the entry, link to it, or add matching `match` strings."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MALFORMED_METADATA: FindingClass.certain,
        CODE_FORBIDDEN_SYNONYM: FindingClass.certain,
        CODE_UNLINKED_TERM: FindingClass.hint,
        CODE_UNUSED_TERM: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_UNLINKED_TERM: Answer.fix("link the term's first use to its glossary entry"),
        CODE_UNUSED_TERM: Answer.line(
            "an entry kept for its readers keeps a reasoned ignore comment above its heading"
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        glossary_rel = Path(graph.config.checks.glossary_discipline.glossary_path)
        glossary_abs = graph.repo_root / glossary_rel
        if not glossary_abs.is_file():
            return []

        try:
            glossary_text = glossary_abs.read_text(encoding="utf-8")
        except OSError:
            return []

        entries, _anti, parse_issues = _parse_glossary_entries(glossary_text)
        if not entries and not parse_issues:
            return []

        node_caches = [
            _NodeGlossaryCache(
                node=node,
                masked_body=_masked_body(node.body),
                glossary_anchors=frozenset(_linked_glossary_anchors(node, glossary_rel)),
            )
            for node in graph.nodes.values()
        ]
        out: list[Finding] = [
            Finding(
                check=self.name,
                code=CODE_MALFORMED_METADATA,
                severity=Severity.error,
                message=issue.message,
                path=glossary_rel,
                line=issue.line,
            )
            for issue in parse_issues
        ]

        for entry in entries:
            if not entry.has_metadata:
                continue

            out.extend(self._forbidden_synonym_findings(node_caches, entry))
            out.extend(self._unlinked_term_findings(node_caches, entry, glossary_rel))
            if self._entry_is_unused(node_caches, entry):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_UNUSED_TERM,
                        severity=Severity.warning,
                        message=f"glossary term '{entry.term}' is declared but unused",
                        path=glossary_rel,
                        line=entry.line,
                        suggestion=(
                            "remove the entry, link to it, or add explicit `match` strings "
                            "used by docs"
                        ),
                    )
                )

        return out

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Wrap the first use of a glossary term with its anchor link.

        Edits prose, so it requires `--confirm`. Gated on the info-level
        unlinked-term findings already emitted for a node.
        """
        if graph.config is None or graph.repo_root is None:
            return []
        flagged_paths = {
            finding.path
            for finding in findings
            if finding.check == self.name and finding.severity == Severity.info
        }
        if not flagged_paths:
            return []

        glossary_rel = Path(graph.config.checks.glossary_discipline.glossary_path)
        glossary_abs = graph.repo_root / glossary_rel
        if not glossary_abs.is_file():
            return []
        try:
            glossary_text = glossary_abs.read_text(encoding="utf-8")
        except OSError:
            return []

        entries, _anti, _issues = _parse_glossary_entries(glossary_text)
        glossary_posix = glossary_rel.as_posix()
        flagged = [
            node
            for node in graph.nodes.values()
            if node.path in flagged_paths and node.path.as_posix() != glossary_posix
        ]
        linked = {node.id: _linked_glossary_anchors(node, glossary_rel) for node in flagged}

        out: list[Fix] = []
        for entry in entries:
            if not entry.has_metadata:
                continue
            anchor = slugify(entry.term)
            for node in flagged:
                if anchor in linked[node.id]:
                    continue
                if (
                    _earliest_match(
                        _masked_for_link(node.body),
                        entry.match_terms,
                        case_sensitive=entry.case_sensitive,
                    )
                    is None
                ):
                    continue
                rel = posixpath.relpath(glossary_posix, node.path.parent.as_posix())
                out.append(
                    Fix(
                        path=node.path,
                        description=(
                            f"link first use of '{entry.term}' to {glossary_posix}#{anchor} "
                            f"in {node.path.as_posix()}"
                        ),
                        apply=_autolink_apply(
                            entry.match_terms,
                            case_sensitive=entry.case_sensitive,
                            link=f"{rel}#{anchor}",
                        ),
                        requires_confirm=True,
                    )
                )
        return out

    def _forbidden_synonym_findings(
        self,
        node_caches: list[_NodeGlossaryCache],
        entry: GlossaryEntry,
    ) -> list[Finding]:
        out: list[Finding] = []
        for synonym in entry.forbidden_synonyms:
            for cache in node_caches:
                node = cache.node
                line = _first_match_line(
                    cache.masked_body,
                    synonym,
                    case_sensitive=entry.case_sensitive,
                )
                if line is None:
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_FORBIDDEN_SYNONYM,
                        severity=Severity.error,
                        message=(
                            f"forbidden synonym '{synonym}' used; canonical term is '{entry.term}'"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        line=node.file_line(line),
                        suggestion=f"use '{entry.term}' instead",
                    )
                )
        return out

    def _unlinked_term_findings(
        self,
        node_caches: list[_NodeGlossaryCache],
        entry: GlossaryEntry,
        glossary_rel: Path,
    ) -> list[Finding]:
        out: list[Finding] = []
        anchor = slugify(entry.term)
        for cache in node_caches:
            node = cache.node
            if anchor in cache.glossary_anchors:
                continue
            matching_lines = [
                line
                for match_term in entry.match_terms
                if (
                    line := _first_match_line(
                        cache.masked_body,
                        match_term,
                        case_sensitive=entry.case_sensitive,
                    )
                )
                is not None
            ]
            if not matching_lines:
                continue
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_UNLINKED_TERM,
                    severity=Severity.info,
                    message=(
                        f"glossary term '{entry.term}' used without linking to "
                        f"{glossary_rel.as_posix()}#{anchor}"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    line=node.file_line(min(matching_lines)),
                    suggestion=f"link first use to {glossary_rel.as_posix()}#{anchor}",
                )
            )
        return out

    def _entry_is_unused(
        self,
        node_caches: list[_NodeGlossaryCache],
        entry: GlossaryEntry,
    ) -> bool:
        anchor = slugify(entry.term)
        for cache in node_caches:
            if anchor in cache.glossary_anchors:
                return False
            for match_term in entry.match_terms:
                # Unmasked: an identifier-spelled term is only ever written in a code
                # span, which the masked body blanks.
                if _has_match(cache.node.body, match_term, case_sensitive=entry.case_sensitive):
                    return False
        return True
