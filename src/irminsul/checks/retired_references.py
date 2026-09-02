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
from irminsul.regen.agents_md import GENERATED_END, GENERATED_START, manifest_rel_path
from irminsul.surface import derive_surface

_REFERENCE_DEFINITION_RE = re.compile(r"^\s{0,3}\[([^\]\n]+)\]:\s*(?:<([^>\n]+)>|(\S+))")
_INLINE_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\n]+)\)")
_INLINE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")
_REFERENCE_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\[([^\]\n]*)\]")
_REFERENCE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]")
_AUTOLINK_RE = re.compile(r"<(?:(?:https?|mailto):[^>\n]+)>")
_BARE_URL_RE = re.compile(r"(?:https?|mailto):[^\s)>]+")
_MARKUP_RE = re.compile(r"[`*_~]")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


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
    unmatched_marker_line: int | None = None


@dataclass(frozen=True)
class _LinkedLabel:
    token: str
    label: str
    destination: str


CODE_INACTIVE_RETIREMENT = "retired-references/inactive-retirement"
CODE_RETIREMENT_STILL_LIVE = "retired-references/retirement-still-live"
CODE_AMBIGUOUS_RETIREMENT = "retired-references/ambiguous-retirement"
CODE_RETIRED_REFERENCE = "retired-references/retired-reference"
CODE_UNMATCHED_GENERATED_MARKER = "retired-references/unmatched-generated-marker"


class RetiredReferencesCheck:
    name: ClassVar[str] = "retired-references"
    # The check emits both: stale guidance and an unmatched generated marker are
    # errors, the tombstone-hygiene findings are warnings. The declaration names
    # the blocking one, matching `RfcLifecycleIntegrityCheck`, the other
    # mixed-severity hard check.
    default_severity: ClassVar[Severity] = Severity.error
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
        CODE_UNMATCHED_GENERATED_MARKER: (
            "A generated-region start marker has no matching end marker, which would "
            "leave everything below it unaudited. Close the region with the end marker "
            "or remove the start marker."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None or graph.config is None:
            return []

        rules, findings = _retirement_registry(graph)
        if not rules:
            return findings

        for source in _guidance_sources(graph):
            if source.unmatched_marker_line is not None:
                findings.append(_unmatched_marker_finding(source))
            # An ADR has to be able to say what it retired, so it is never
            # audited against its own tombstones. Every other document is,
            # including other ADRs.
            applicable = [rule for rule in rules if rule.owner.path != source.path]
            if not applicable:
                continue
            visible_lines, definitions = _visible_source_lines(source.lines)
            occurrences: dict[tuple[str, str], tuple[_RetirementRule, int, int]] = {}
            for lineno, line in visible_lines:
                visible, linked_labels = _visible_markdown_line(
                    line,
                    source.path,
                    definitions,
                )
                handled: set[tuple[str, str]] = set()
                for rule in applicable:
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
        key = (rule.entry.kind, _dedup_phrase_key(rule.phrase, rule.entry.kind))
        by_phrase.setdefault(key, []).append(rule)

    active: list[_RetirementRule] = []
    for key in sorted(by_phrase, key=lambda item: (item[0].value, item[1])):
        group = sorted(
            by_phrase[key],
            key=lambda rule: (rule.owner.path.as_posix(), rule.entry.id),
        )
        canonical = group[0]
        active.append(canonical)
        for duplicate in group[1:]:
            if duplicate.identity == canonical.identity:
                # One tombstone deliberately listing both spellings — `Topology
                # A` for the proper name plus `topology a` to fold case. Both
                # patterns stay active; the per-line identity dedup already
                # makes a line matching both count once.
                active.append(duplicate)
                continue
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


def _folds_case(phrase: str, kind: RetirementKindEnum) -> bool:
    """Whether this phrase is matched case-insensitively.

    Only `concept` phrases ever fold case, and only the ones written entirely
    in lower case — the "smart case" rule that `rg` and `vim` use. A concept is
    prose, so `docs-only topology` has to catch `Docs-Only Topology` at the
    start of a sentence or inside a heading. But a concept named with a capital
    is a proper name, and folding its case turns short ones into landmines: the
    two-token `Topology A` matched the ordinary English "whatever topology a
    project picks", so the tombstone failed the build on prose that never
    mentioned the retired thing. Word boundaries do not help — "topology a" is
    a whole-token match there. Case is the signal that separates the name from
    the words it is spelled with, so a capitalised declaration keeps it.

    The cost is that a capitalised phrase no longer catches an all-lowercase
    reference to it. That is the right trade: guidance that names a retired
    concept spells it the way the tombstone declares it, and a tombstone that
    wants both spellings can list both in `matches:`.
    """
    if kind != RetirementKindEnum.concept:
        return False
    return not any(char.isupper() for char in phrase)


def _compile_phrase(phrase: str, kind: RetirementKindEnum) -> re.Pattern[str]:
    core = r"\s+".join(re.escape(part) for part in phrase.split())
    flags = re.IGNORECASE if _folds_case(phrase, kind) else 0
    return re.compile(rf"(?<![\w-]){core}(?![\w-])", flags)


def _dedup_phrase_key(phrase: str, kind: RetirementKindEnum) -> str:
    """The key two declarations must share to count as the same retirement.

    Every concept phrase folds case here — including the capitalised ones that
    *match* case-sensitively. The registry's question is not "would these
    patterns fire on the same line" but "do two ADRs claim the same retired
    thing": `docs-only topology` and `Docs-Only Topology` name one concept,
    and keying them apart let both rules run, so one guidance line drew two
    hard errors and no `ambiguous-retirement` warning ever fired. The
    smart-case *matching* semantics are untouched — `_folds_case` still
    decides how each surviving pattern compiles.
    """
    normalized = " ".join(phrase.split())
    return normalized.casefold() if kind == RetirementKindEnum.concept else normalized


def _guidance_sources(graph: DocGraph) -> list[_GuidanceSource]:
    assert graph.repo_root is not None
    assert graph.config is not None

    sources: list[_GuidanceSource] = []
    for node in sorted(graph.nodes.values(), key=lambda item: item.path.as_posix()):
        if node.frontmatter.status != StatusEnum.stable:
            continue
        # RFCs are frozen historical records (ADR-0016) and are never edited,
        # so auditing them would report findings nobody is allowed to fix.
        # ADRs are audited: they are current decisions, and the one that owns a
        # tombstone is exempted from it in `run` rather than wholesale here.
        if _is_rfc_path(node.path):
            continue
        lines, unmatched = _file_lines(graph.repo_root / node.path, blank_generated=False)
        sources.append(
            _GuidanceSource(
                path=node.path,
                doc_id=node.id,
                lines=lines,
                unmatched_marker_line=unmatched,
            )
        )

    docs_root = Path(graph.config.paths.docs_root)
    manifest = _repo_relative(graph.repo_root, manifest_rel_path(graph.config))
    # The agent guides are the highest-traffic guidance in the repo — `irminsul
    # init` tells every user to point their agent at them — and none of them is
    # a graph node: the AGENTS.md files are in EXEMPT_TOPLEVEL_NAMES and
    # CLAUDE.md lives outside docs_root entirely.
    current_files = {
        Path("README.md"),
        Path("AGENTS.md"),
        Path("CLAUDE.md"),
        docs_root / "README.md",
        docs_root / "AGENTS.md",
        docs_root / "GLOSSARY.md",
        docs_root / "CONTRIBUTING.md",
    }
    for path in sorted(current_files, key=lambda item: item.as_posix()):
        absolute = graph.repo_root / path
        if absolute.is_file():
            relative = _repo_relative(graph.repo_root, path)
            lines, unmatched = _file_lines(absolute, blank_generated=relative == manifest)
            sources.append(
                _GuidanceSource(
                    path=relative,
                    doc_id=None,
                    lines=lines,
                    unmatched_marker_line=unmatched,
                )
            )
    return sources


def _repo_relative(repo_root: Path, path: Path) -> Path:
    try:
        return path.relative_to(repo_root)
    except ValueError:
        return path


def _is_rfc_path(path: Path) -> bool:
    parts = path.as_posix().split("/")
    return "80-evolution" in parts and "rfcs" in parts


def _file_lines(
    path: Path, *, blank_generated: bool
) -> tuple[tuple[tuple[int, str], ...], int | None]:
    """Every line of the file, numbered, with the agent manifest's
    machine-generated region blanked and the line number of an unmatched
    generated-start marker.

    Frontmatter is included: a retired name is just as misleading in a `title:`
    or `summary:` as in prose, and the tombstone owner's own `matches:` list is
    already exempted by the declaring-ADR rule.

    The `regen agents-md` region is not. It is derived output whose rows are the
    titles of the documents it indexes — including RFCs, whose titles ADR-0016
    freezes — so a finding there names a line no one may edit and that `regen`
    would rewrite identically. Line numbers are preserved so every other line in
    the file still reports accurately.

    Only the manifest carries that region, so only the manifest is read for its
    markers. Anywhere else the marker text is an example — the checks guide and
    ADR-0004 both discuss it — and reading an example as a region either failed
    the build on it or let a fenced pair hide stale guidance from a hard check.
    Inside the manifest a fenced example is skipped for the same reason, and a
    start and end on one line close the region on that line.

    Only *balanced* markers blank anything, and the line number of an unmatched
    start marker comes back with the lines. A start marker used to open the
    region and never close it, so one stray line — a bad merge, a half-written
    manifest — silently switched a hard check off for the rest of the file. A
    suppression that broad has to be reported, not inferred.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not blank_generated:
        return tuple(enumerate(lines, start=1)), None

    generated: set[int] = set()
    open_start: int | None = None
    in_fence = False
    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        rest = line
        if open_start is None and GENERATED_START in rest:
            open_start = index
            rest = rest[rest.index(GENERATED_START) + len(GENERATED_START) :]
        if open_start is not None and GENERATED_END in rest:
            generated.update(range(open_start, index + 1))
            open_start = None
    out = tuple((index + 1, "" if index in generated else line) for index, line in enumerate(lines))
    return out, None if open_start is None else open_start + 1


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
    folds_case = _folds_case(rule.phrase, rule.entry.kind)
    for linked in linked_labels:
        actual_label = _citation_label(linked.label)
        labels_match = (
            actual_label.casefold() == expected_label.casefold()
            if folds_case
            else actual_label == expected_label
        )
        replacement = (
            ""
            if labels_match and linked.destination == rule.owner.path.as_posix()
            else linked.label
        )
        visible = visible.replace(linked.token, replacement)
    return visible


def _unmatched_marker_finding(source: _GuidanceSource) -> Finding:
    return Finding(
        check=RetiredReferencesCheck.name,
        code=CODE_UNMATCHED_GENERATED_MARKER,
        # An error for the same reason the stale-guidance finding is one: the
        # marker's effect is to stop this hard check reading the rest of the
        # file, and a suppression nobody declared has to fail rather than warn.
        severity=Severity.error,
        category="unmatched-generated-marker",
        message="generated-region start marker has no matching end marker",
        path=source.path,
        doc_id=source.doc_id,
        line=source.unmatched_marker_line,
        suggestion=(
            f"Close the region with `{GENERATED_END}`, or remove the start marker — "
            "everything below it would otherwise go unaudited"
        ),
        data={
            "problem": "unmatched-generated-marker",
            "marker": GENERATED_START,
        },
    )


def _retired_reference_finding(
    source: _GuidanceSource,
    lineno: int,
    rule: _RetirementRule,
    occurrences: int,
) -> Finding:
    return Finding(
        check=RetiredReferencesCheck.name,
        code=CODE_RETIRED_REFERENCE,
        # An error, not a warning: ADR-0022 nominates this audit as the thing
        # that makes stale guidance fail, and CI runs no `--strict`. A warning
        # here reports and never blocks, which is what let a retired command
        # survive in a shipped ADR.
        severity=Severity.error,
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
