"""Audit current guidance against ADR-owned retirement tombstones."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar
from urllib.parse import unquote, urlsplit

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import (
    AudienceEnum,
    RetirementEntry,
    RetirementKindEnum,
    StatusEnum,
)
from irminsul.surface import derive_surface

_REFERENCE_DEFINITION_RE = re.compile(r"^\s{0,3}\[([^\]\n]+)\]:\s*(?:<([^>\n]+)>|(\S+))")
_INLINE_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\n]+)\)")
_INLINE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")
_REFERENCE_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\[([^\]\n]*)\]")
_REFERENCE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]")
_AUTOLINK_RE = re.compile(r"<(?:(?:https?|mailto):[^>\n]+)>")
_BARE_URL_RE = re.compile(r"(?:https?|mailto):[^\s)>]+")
_MARKUP_RE = re.compile(r"[`*_~]")


@dataclass(frozen=True)
class _RetirementRule:
    owner: DocNode
    entry: RetirementEntry
    phrase: str
    pattern: re.Pattern[str]

    @property
    def identity(self) -> tuple[str, str]:
        return (self.owner.path.as_posix(), self.entry.id)


@dataclass(frozen=True)
class _GuidanceSource:
    path: Path
    doc_id: str | None
    lines: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class _LinkedLabel:
    token: str
    label: str
    destination: str


CODE_INACTIVE_RETIREMENT = "retired-references/inactive-retirement"
CODE_RETIREMENT_STILL_LIVE = "retired-references/retirement-still-live"
CODE_AMBIGUOUS_RETIREMENT = "retired-references/ambiguous-retirement"
CODE_RETIRED_REFERENCE = "retired-references/retired-reference"


class RetiredReferencesCheck:
    name: ClassVar[str] = "retired-references"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_INACTIVE_RETIREMENT: (
            "A `retires` declaration is inactive because its owner is not a stable ADR. "
            "Move the declarations to the stable ADR that approved the retirement."
        ),
        CODE_RETIREMENT_STILL_LIVE: (
            "A retired CLI identity is still present in the current derived surface. "
            "Remove the tombstone if the command was restored, or remove the live "
            "command if the retirement still governs."
        ),
        CODE_AMBIGUOUS_RETIREMENT: (
            "The same retired phrase is declared by more than one ADR. Keep one "
            "authoritative tombstone."
        ),
        CODE_RETIRED_REFERENCE: (
            "Current guidance references a phrase, symbol, or concept an ADR has "
            "declared retired. Follow the retirement's guidance and remove or replace "
            "the reference."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None or graph.config is None:
            return []

        rules, findings = _retirement_registry(graph)
        if not rules:
            return findings

        for source in _guidance_sources(graph):
            visible_lines, definitions = _visible_source_lines(source.lines)
            occurrences: dict[tuple[str, str], tuple[_RetirementRule, int, int]] = {}
            for lineno, line in visible_lines:
                visible, linked_labels = _visible_markdown_line(
                    line,
                    source.path,
                    definitions,
                )
                handled: set[tuple[str, str]] = set()
                for rule in rules:
                    auditable = _auditable_line(visible, linked_labels, rule)
                    if rule.identity in handled or rule.pattern.search(auditable) is None:
                        continue
                    handled.add(rule.identity)
                    existing = occurrences.get(rule.identity)
                    if existing is None:
                        occurrences[rule.identity] = (rule, lineno, 1)
                    else:
                        occurrences[rule.identity] = (existing[0], existing[1], existing[2] + 1)
            findings.extend(
                _retired_reference_finding(source, first_line, rule, count)
                for rule, first_line, count in occurrences.values()
            )

        return findings


def _retirement_registry(
    graph: DocGraph,
) -> tuple[list[_RetirementRule], list[Finding]]:
    candidates: list[_RetirementRule] = []
    findings: list[Finding] = []
    live_cli_identities: set[str] | None = None
    for node in sorted(graph.nodes.values(), key=lambda item: item.path.as_posix()):
        if not node.frontmatter.retires:
            continue
        if not _is_authoritative_owner(node):
            findings.append(
                Finding(
                    check=RetiredReferencesCheck.name,
                    code=CODE_INACTIVE_RETIREMENT,
                    severity=Severity.warning,
                    category="inactive-retirement",
                    message=(
                        f"retirement declarations on '{node.id}' are inactive because "
                        "their owner is not a stable ADR"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="Move the declarations to the stable ADR that approved the retirement",
                    data={
                        "problem": "inactive-retirement",
                        "reason": "owner-not-stable-adr",
                    },
                )
            )
            continue
        for entry in node.frontmatter.retires:
            if entry.kind == RetirementKindEnum.cli_command:
                if live_cli_identities is None:
                    assert graph.repo_root is not None
                    assert graph.config is not None
                    live_cli_identities = {
                        item.identity
                        for item in derive_surface(graph.repo_root, graph.config, "cli")
                    }
                assert entry.surface_identity is not None
                if entry.surface_identity in live_cli_identities:
                    findings.append(
                        Finding(
                            check=RetiredReferencesCheck.name,
                            code=CODE_RETIREMENT_STILL_LIVE,
                            severity=Severity.warning,
                            category="retirement-still-live",
                            message=(
                                f"retired CLI identity '{entry.surface_identity}' is present "
                                "in the current derived surface"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion=(
                                "Remove the tombstone if the command was restored, or remove "
                                "the live command if the retirement still governs"
                            ),
                            data={
                                "problem": "retirement-still-live",
                                "kind": entry.kind.value,
                                "retirement-id": entry.id,
                                "surface-identity": entry.surface_identity,
                            },
                        )
                    )
                    continue
            for phrase in entry.matches:
                candidates.append(
                    _RetirementRule(
                        owner=node,
                        entry=entry,
                        phrase=phrase,
                        pattern=_compile_phrase(phrase, entry.kind),
                    )
                )

    by_phrase: dict[tuple[RetirementKindEnum, str], list[_RetirementRule]] = {}
    for rule in candidates:
        key = (rule.entry.kind, _normalize_phrase(rule.phrase, rule.entry.kind))
        by_phrase.setdefault(key, []).append(rule)

    active: list[_RetirementRule] = []
    for key in sorted(by_phrase, key=lambda item: (item[0].value, item[1])):
        group = sorted(
            by_phrase[key],
            key=lambda rule: (rule.owner.path.as_posix(), rule.entry.id),
        )
        canonical = group[0]
        if len(group) == 1:
            active.append(canonical)
            continue
        for duplicate in group[1:]:
            findings.append(
                Finding(
                    check=RetiredReferencesCheck.name,
                    code=CODE_AMBIGUOUS_RETIREMENT,
                    severity=Severity.warning,
                    category="ambiguous-retirement",
                    message=(
                        f"retired {duplicate.entry.kind.value} phrase "
                        f"'{duplicate.phrase}' is also declared by '{canonical.owner.id}'"
                    ),
                    path=duplicate.owner.path,
                    doc_id=duplicate.owner.id,
                    suggestion=(
                        f"Keep one authoritative tombstone in {canonical.owner.path.as_posix()}"
                    ),
                    data={
                        "problem": "ambiguous-retirement",
                        "kind": duplicate.entry.kind.value,
                        "match": duplicate.phrase,
                        "declared-by": canonical.owner.path.as_posix(),
                    },
                )
            )

    return sorted(
        active,
        key=lambda rule: (
            -len(rule.phrase),
            rule.owner.path.as_posix(),
            rule.entry.id,
            rule.phrase,
        ),
    ), findings


def _is_authoritative_owner(node: DocNode) -> bool:
    return (
        node.frontmatter.audience == AudienceEnum.adr
        and node.frontmatter.status == StatusEnum.stable
    )


def _compile_phrase(phrase: str, kind: RetirementKindEnum) -> re.Pattern[str]:
    core = r"\s+".join(re.escape(part) for part in phrase.split())
    flags = re.IGNORECASE if kind == RetirementKindEnum.concept else 0
    return re.compile(rf"(?<![\w-]){core}(?![\w-])", flags)


def _normalize_phrase(phrase: str, kind: RetirementKindEnum) -> str:
    normalized = " ".join(phrase.split())
    return normalized.lower() if kind == RetirementKindEnum.concept else normalized


def _guidance_sources(graph: DocGraph) -> list[_GuidanceSource]:
    assert graph.repo_root is not None
    assert graph.config is not None

    sources: list[_GuidanceSource] = []
    for node in sorted(graph.nodes.values(), key=lambda item: item.path.as_posix()):
        if node.frontmatter.status != StatusEnum.stable:
            continue
        if node.frontmatter.audience == AudienceEnum.adr or _is_rfc_path(node.path):
            continue
        sources.append(
            _GuidanceSource(
                path=node.path,
                doc_id=node.id,
                lines=_body_lines(graph.repo_root / node.path),
            )
        )

    docs_root = Path(graph.config.paths.docs_root)
    current_files = {
        Path("README.md"),
        docs_root / "README.md",
        docs_root / "GLOSSARY.md",
        docs_root / "CONTRIBUTING.md",
    }
    for path in sorted(current_files, key=lambda item: item.as_posix()):
        absolute = graph.repo_root / path
        if absolute.is_file():
            try:
                relative = path.relative_to(graph.repo_root)
            except ValueError:
                relative = path
            sources.append(
                _GuidanceSource(
                    path=relative,
                    doc_id=None,
                    lines=tuple(enumerate(absolute.read_text(encoding="utf-8").splitlines(), 1)),
                )
            )
    return sources


def _is_rfc_path(path: Path) -> bool:
    parts = path.as_posix().split("/")
    return "80-evolution" in parts and "rfcs" in parts


def _body_lines(path: Path) -> tuple[tuple[int, str], ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return tuple(enumerate(lines, 1))
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing is None:
        return tuple(enumerate(lines, 1))
    return tuple(enumerate(lines[closing + 1 :], start=closing + 2))


def _visible_source_lines(
    lines: tuple[tuple[int, str], ...],
) -> tuple[list[tuple[int, str]], dict[str, str]]:
    visible: list[tuple[int, str]] = []
    definitions: dict[str, str] = {}
    in_comment = False
    for lineno, line in lines:
        line, in_comment = _strip_html_comments(line, in_comment)
        definition = _REFERENCE_DEFINITION_RE.match(line)
        if definition is not None:
            label = _reference_key(definition.group(1))
            definitions[label] = definition.group(2) or definition.group(3)
            visible.append((lineno, ""))
            continue
        visible.append((lineno, line))
    return visible, definitions


def _strip_html_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    visible: list[str] = []
    cursor = 0
    while cursor < len(line):
        if in_comment:
            end = line.find("-->", cursor)
            if end == -1:
                return "".join(visible), True
            cursor = end + 3
            in_comment = False
            continue
        start = line.find("<!--", cursor)
        if start == -1:
            visible.append(line[cursor:])
            break
        visible.append(line[cursor:start])
        cursor = start + 4
        in_comment = True
    return "".join(visible), in_comment


def _visible_markdown_line(
    line: str,
    source_path: Path,
    definitions: dict[str, str],
) -> tuple[str, list[_LinkedLabel]]:
    linked_labels: list[_LinkedLabel] = []

    line = _INLINE_IMAGE_RE.sub(lambda match: match.group(1), line)
    line = _REFERENCE_IMAGE_RE.sub(lambda match: match.group(1), line)

    def inline_link(match: re.Match[str]) -> str:
        label = match.group(1)
        destination = _link_destination(match.group(2))
        resolved = _resolve_destination(source_path, destination)
        return _linked_label_token(label, resolved, linked_labels)

    def reference_link(match: re.Match[str]) -> str:
        label = match.group(1)
        key = _reference_key(match.group(2) or label)
        destination = definitions.get(key)
        resolved = _resolve_destination(source_path, destination)
        return _linked_label_token(label, resolved, linked_labels)

    line = _INLINE_LINK_RE.sub(inline_link, line)
    line = _REFERENCE_LINK_RE.sub(reference_link, line)
    line = _AUTOLINK_RE.sub("", line)
    line = _BARE_URL_RE.sub("", line)
    return line, linked_labels


def _linked_label_token(
    label: str,
    resolved: str | None,
    linked_labels: list[_LinkedLabel],
) -> str:
    if resolved is None:
        return label
    token = f"\x00irminsul-link-{len(linked_labels)}\x00"
    linked_labels.append(_LinkedLabel(token=token, label=label, destination=resolved))
    return token


def _link_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _resolve_destination(source_path: Path, destination: str | None) -> str | None:
    if not destination:
        return None
    split = urlsplit(destination)
    if split.scheme or split.netloc or not split.path:
        return None
    raw_path = unquote(split.path).replace("\\", "/")
    if raw_path.startswith("/"):
        combined = raw_path.lstrip("/")
    else:
        combined = (PurePosixPath(source_path.parent.as_posix()) / raw_path).as_posix()
    return posixpath.normpath(combined)


def _reference_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def _citation_label(label: str) -> str:
    without_markup = _MARKUP_RE.sub("", label.replace("\\", ""))
    return " ".join(without_markup.split())


def _auditable_line(
    visible: str,
    linked_labels: list[_LinkedLabel],
    rule: _RetirementRule,
) -> str:
    expected_label = _citation_label(rule.phrase)
    for linked in linked_labels:
        actual_label = _citation_label(linked.label)
        labels_match = (
            actual_label.casefold() == expected_label.casefold()
            if rule.entry.kind == RetirementKindEnum.concept
            else actual_label == expected_label
        )
        replacement = (
            ""
            if labels_match and linked.destination == rule.owner.path.as_posix()
            else linked.label
        )
        visible = visible.replace(linked.token, replacement)
    return visible


def _retired_reference_finding(
    source: _GuidanceSource,
    lineno: int,
    rule: _RetirementRule,
    occurrences: int,
) -> Finding:
    return Finding(
        check=RetiredReferencesCheck.name,
        code=CODE_RETIRED_REFERENCE,
        severity=Severity.warning,
        category="retired-reference",
        message=(f"current guidance references retired {rule.entry.kind.value} '{rule.phrase}'"),
        path=source.path,
        doc_id=source.doc_id,
        line=lineno,
        suggestion=(
            f"{rule.entry.guidance} For historical discussion, link the exact phrase "
            f"to {rule.owner.path.as_posix()}"
        ),
        data={
            "problem": "retired-reference",
            "kind": rule.entry.kind.value,
            "match": rule.phrase,
            "retirement-id": rule.entry.id,
            "declared-by": rule.owner.path.as_posix(),
            "guidance": rule.entry.guidance,
            "occurrences": str(occurrences),
        },
    )
