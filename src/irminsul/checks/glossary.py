"""Glossary discipline check.

RFC 0019 makes glossary enforcement opt-in per term: a heading in
`GLOSSARY.md` may declare explicit match strings, forbidden synonyms, and case
sensitivity. Bare glossary headings remain valid and still power the older
"do not redefine glossary terms elsewhere" rule.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar

from markdown_it import MarkdownIt

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.docgraph_index import slugify

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_KNOWN_METADATA_KEYS = frozenset({"match", "forbidden_synonyms", "case_sensitive"})
_FENCE_RE = re.compile(r"(?ms)^ {0,3}(```|~~~).*?^ {0,3}\1\s*$")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


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


def _parse_glossary_terms(glossary_text: str) -> tuple[set[str], set[str]]:
    """Return bare glossary terms and anti-glossary entries.

    Kept as a small helper for callers/tests that only need the legacy term
    inventory.
    """
    entries, anti, _issues = _parse_glossary_entries(glossary_text)
    return {entry.term for entry in entries}, anti


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


def _doc_redefines_term(body: str, term: str) -> bool:
    pattern = re.compile(
        rf"(?m)^#{{1,6}}\s+{re.escape(term)}\s*$" rf"|^\*\*{re.escape(term)}\*\*:?\s*$"
    )
    return pattern.search(body) is not None


def _masked_body(body: str) -> str:
    masked = body
    for pattern in (_FENCE_RE, _INLINE_CODE_RE):
        masked = pattern.sub(lambda match: _blank_preserve_newlines(match.group(0)), masked)
    return masked


def _blank_preserve_newlines(text: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in text)


def _first_match_line(body: str, term: str, *, case_sensitive: bool) -> int | None:
    match = _term_pattern(term, case_sensitive=case_sensitive).search(_masked_body(body))
    if match is None:
        return None
    return body[: match.start()].count("\n") + 1


def _has_match(body: str, term: str, *, case_sensitive: bool) -> bool:
    return _first_match_line(body, term, case_sensitive=case_sensitive) is not None


def _term_pattern(term: str, *, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags)


def _doc_links_to_glossary_anchor(
    node: DocNode,
    glossary_rel: Path,
    anchor: str,
    md: MarkdownIt,
) -> bool:
    tokens = md.parse(node.body)
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        for child in token.children:
            if child.type != "link_open":
                continue
            href = child.attrGet("href")
            if isinstance(href, str) and _href_targets_glossary_anchor(
                node, href, glossary_rel, anchor
            ):
                return True
    return False


def _href_targets_glossary_anchor(
    src_node: DocNode,
    href: str,
    glossary_rel: Path,
    anchor: str,
) -> bool:
    target, raw_anchor = _split_href(href)
    if raw_anchor != anchor:
        return False
    if not target or "://" in target or target.startswith(("mailto:", "tel:")):
        return False
    doc_parent = PurePosixPath(src_node.path.as_posix()).parent
    raw = doc_parent / target
    parts: list[str] = []
    for part in raw.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return Path(*parts).as_posix() == glossary_rel.as_posix()


def _split_href(href: str) -> tuple[str, str | None]:
    target, sep, anchor = href.partition("#")
    return target, anchor if sep else None


class GlossaryDisciplineCheck:
    name: ClassVar[str] = "glossary-discipline"
    default_severity: ClassVar[Severity] = Severity.warning

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

        md = MarkdownIt("commonmark")
        glossary_path_posix = glossary_rel.as_posix()
        out: list[Finding] = [
            Finding(
                check=self.name,
                severity=Severity.warning,
                message=issue.message,
                path=glossary_rel,
                line=issue.line,
            )
            for issue in parse_issues
        ]

        for entry in entries:
            slug = slugify(entry.term)
            for node in graph.nodes.values():
                if node.path.as_posix() == glossary_path_posix:
                    continue
                if _doc_redefines_term(node.body, entry.term):
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.warning,
                            message=(
                                f"glossary term '{entry.term}' redefined in "
                                f"{node.path.as_posix()}; glossary is canonical"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion=f"link to {glossary_path_posix}#{slug} instead",
                        )
                    )

            if not entry.has_metadata:
                continue

            out.extend(self._forbidden_synonym_findings(graph, entry))
            out.extend(self._unlinked_term_findings(graph, entry, glossary_rel, md))
            if self._entry_is_unused(graph, entry, glossary_rel, md):
                out.append(
                    Finding(
                        check=self.name,
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

    def _forbidden_synonym_findings(
        self,
        graph: DocGraph,
        entry: GlossaryEntry,
    ) -> list[Finding]:
        out: list[Finding] = []
        for synonym in entry.forbidden_synonyms:
            for node in graph.nodes.values():
                line = _first_match_line(node.body, synonym, case_sensitive=entry.case_sensitive)
                if line is None:
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=(
                            f"forbidden synonym '{synonym}' used; canonical term is '{entry.term}'"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        line=line,
                        suggestion=f"use '{entry.term}' instead",
                    )
                )
        return out

    def _unlinked_term_findings(
        self,
        graph: DocGraph,
        entry: GlossaryEntry,
        glossary_rel: Path,
        md: MarkdownIt,
    ) -> list[Finding]:
        out: list[Finding] = []
        anchor = slugify(entry.term)
        for node in graph.nodes.values():
            if _doc_links_to_glossary_anchor(node, glossary_rel, anchor, md):
                continue
            matching_lines = [
                line
                for match_term in entry.match_terms
                if (
                    line := _first_match_line(
                        node.body,
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
                    severity=Severity.info,
                    message=(
                        f"glossary term '{entry.term}' used without linking to "
                        f"{glossary_rel.as_posix()}#{anchor}"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    line=min(matching_lines),
                    suggestion=f"link first use to {glossary_rel.as_posix()}#{anchor}",
                )
            )
        return out

    def _entry_is_unused(
        self,
        graph: DocGraph,
        entry: GlossaryEntry,
        glossary_rel: Path,
        md: MarkdownIt,
    ) -> bool:
        anchor = slugify(entry.term)
        for node in graph.nodes.values():
            if _doc_links_to_glossary_anchor(node, glossary_rel, anchor, md):
                return False
            for match_term in entry.match_terms:
                if _has_match(node.body, match_term, case_sensitive=entry.case_sensitive):
                    return False
        return True
