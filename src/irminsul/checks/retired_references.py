"""Audit current guidance against ADR-owned retirement tombstones."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

from irminsul.checks.base import Finding, FindingClass, Severity, carries_certain_findings
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode, is_decision, is_rfc
from irminsul.docgraph_index import resolve_href
from irminsul.frontmatter import (
    RetirementEntry,
    RetirementKindEnum,
    StatusEnum,
)
from irminsul.frontmatter_edit import is_frontmatter_delimiter
from irminsul.marked_region import MalformedRegion, find_region
from irminsul.regen.agents_md import GENERATED_END, GENERATED_START, manifest_rel_path

_REFERENCE_DEFINITION_RE = re.compile(r"^\s{0,3}\[([^\]\n]+)\]:\s*(?:<([^>\n]+)>|(\S+))")
_INLINE_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\n]+)\)")
_INLINE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")
_REFERENCE_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\[([^\]\n]*)\]")
_REFERENCE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]")
_AUTOLINK_RE = re.compile(r"<(?:(?:https?|mailto):[^>\n]+)>")
_BARE_URL_RE = re.compile(r"(?:https?|mailto):[^\s)>]+")
_MARKUP_RE = re.compile(r"[`*_~]")
_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|$)")
# What `_visible_markdown_line` and `_strip_html_comments` replace or drop before the phrases
# are searched: a link keeps only its label, and URLs and comments vanish. Wrapping a phrase in
# a link must not start inside one of them.
_LINK_LIKE_RES = (
    _INLINE_IMAGE_RE,
    _INLINE_LINK_RE,
    _REFERENCE_IMAGE_RE,
    _REFERENCE_LINK_RE,
    _AUTOLINK_RE,
    _BARE_URL_RE,
    _HTML_COMMENT_RE,
)


@dataclass(frozen=True)
class RetirementRule:
    owner: DocNode
    entry: RetirementEntry
    phrase: str
    pattern: re.Pattern[str]
    folds_case: bool
    owner_path: str
    expected_label: str
    """The phrase as a link label would have to spell it, case-folded when the rule folds."""
    identity: tuple[str, str]


@dataclass(frozen=True)
class _RuleScan:
    """Every active rule compiled together, so a line is read once for all of them."""

    rules: tuple[RetirementRule, ...]
    any_rule: re.Pattern[str]
    """Matches wherever at least one rule's own pattern does."""

    @classmethod
    def build(cls, rules: Sequence[RetirementRule]) -> _RuleScan:
        alternatives = (
            f"(?i:{_phrase_core(rule.phrase)})" if rule.folds_case else _phrase_core(rule.phrase)
            for rule in rules
        )
        return cls(
            rules=tuple(rules),
            any_rule=re.compile(rf"(?<![\w-])(?:{'|'.join(alternatives)})(?![\w-])"),
        )

    def applicable_to(self, source_path: Path) -> list[RetirementRule]:
        return [rule for rule in self.rules if rule.owner.path != source_path]


@dataclass(frozen=True)
class _GuidanceSource:
    path: Path
    doc_id: str | None
    lines: tuple[tuple[int, str], ...]
    unmatched_marker_line: int | None
    unreadable: str | None = None
    """Why the file could not be read, when it could not.

    Every other reader of these files skips an unreadable one, so without this a run would
    exit clean having checked none of its links, code references, retired-record mentions or
    ignore comments."""


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
CODE_GUIDANCE_UNREADABLE = "retired-references/guidance-unreadable"


class RetiredReferencesCheck:
    name: ClassVar[str] = "retired-references"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_INACTIVE_RETIREMENT: (
            "A `retires` declaration is inactive because its owner is not a stable ADR. "
            "Move the declarations to the stable ADR that approved the retirement."
        ),
        CODE_RETIREMENT_STILL_LIVE: (
            "A retired CLI identity is still present in the current derived surface, so "
            "the tombstone and the code disagree. Decide which is right: if the command "
            "was deliberately restored, retire the tombstone in a new decision record; if "
            "the retirement still governs, the command's removal is a code change someone "
            "has to make and approve, not a way to clear this finding."
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
            "A generated-region start marker has no matching end marker, so the manifest's "
            "generated rows below it are audited as prose. Close the region with the end "
            "marker or remove the start marker."
        ),
        CODE_GUIDANCE_UNREADABLE: (
            "A guidance file named by `paths.extra_docs` cannot be read as UTF-8, so none of "
            "its links, code references, retired-record mentions or ignore comments were "
            "checked by anything. Every reader skips it, which made the run look clean. Save "
            "it as UTF-8, or drop it from `paths.extra_docs`."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_INACTIVE_RETIREMENT: FindingClass.certain,
        CODE_RETIREMENT_STILL_LIVE: FindingClass.certain,
        CODE_AMBIGUOUS_RETIREMENT: FindingClass.certain,
        CODE_RETIRED_REFERENCE: FindingClass.certain,
        CODE_UNMATCHED_GENERATED_MARKER: FindingClass.certain,
        CODE_GUIDANCE_UNREADABLE: FindingClass.certain,
    }
    #: A guidance file that cannot be read is a file every check silently skips —
    #: links, code references, retired references and ignore comments all stop seeing
    #: it. Baselining that would turn the one finding saying so back into a green run,
    #: which is what this set exists to refuse: the same reason an unusable suppression
    #: marker may not be hidden, reached from coverage rather than from a marker.
    audits_suppression: ClassVar[frozenset[str]] = frozenset({CODE_GUIDANCE_UNREADABLE})

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None or graph.config is None:
            return []

        rules, findings = retirement_registry(graph)
        sources = _guidance_sources(graph)
        # Before the no-rules exit below. A file nothing can read is unaudited whether or not
        # any record retired anything, and `links`, `code-references` and `ignore-comments`
        # all skip the same file — so this is the one place that would say so, and gating it
        # on there being retirement rules would leave a repository with none quiet.
        findings += [
            _unreadable_guidance_finding(source) for source in sources if source.unreadable
        ]
        if not rules:
            return findings

        scan = _RuleScan.build(rules)
        for source in sources:
            if source.unmatched_marker_line is not None:
                findings.append(_unmatched_marker_finding(source))
            findings.extend(
                _retired_reference_finding(source, first_line, rule, count)
                for rule, first_line, count in _occurrences(
                    source.lines, source.path, scan
                ).values()
            )

        return findings


def _occurrences(
    lines: tuple[tuple[int, str], ...],
    source_path: Path,
    scan: _RuleScan,
) -> dict[tuple[str, str], tuple[RetirementRule, int, int]]:
    """Each rule the lines of `source_path` trip, with the first line and the count.

    An ADR has to be able to say what it retired, so it is never audited against its own
    tombstones. Every other document is, including other ADRs.
    """
    applicable = scan.applicable_to(source_path)
    occurrences: dict[tuple[str, str], tuple[RetirementRule, int, int]] = {}
    if not applicable:
        return occurrences
    by_owner: dict[str, list[int]] = {}
    for index, rule in enumerate(applicable):
        by_owner.setdefault(rule.owner_path, []).append(index)
    visible_lines, definitions = _visible_source_lines(lines)
    for lineno, line in visible_lines:
        visible, linked_labels = _visible_markdown_line(line, source_path, definitions)
        for rule in _rules_found_on_line(visible, linked_labels, applicable, by_owner, scan):
            existing = occurrences.get(rule.identity)
            if existing is None:
                occurrences[rule.identity] = (rule, lineno, 1)
            else:
                occurrences[rule.identity] = (existing[0], existing[1], existing[2] + 1)
    return occurrences


def _rules_found_on_line(
    visible: str,
    linked_labels: list[_LinkedLabel],
    applicable: list[RetirementRule],
    by_owner: dict[str, list[int]],
    scan: _RuleScan,
) -> list[RetirementRule]:
    """The first rule of each retirement whose pattern matches this line, in rule order.

    A rule sees the line with every link label restored, except a link to the record that
    owns the rule, whose label is dropped when it is the retired phrase itself — the
    exemption `_auditable_line` applies. Only a rule owned by a record this line links to
    can see anything else, so every other rule reads the one restored line, and a single
    scan of it for all rules at once rules most lines out before any rule is tried alone.
    """
    restored = visible
    exempting: set[int] = set()
    for linked in linked_labels:
        restored = restored.replace(linked.token, linked.label)
        exempting.update(by_owner.get(linked.destination, ()))
    restored_hit = scan.any_rule.search(restored) is not None
    if not restored_hit and not exempting:
        return []
    found: list[RetirementRule] = []
    handled: set[tuple[str, str]] = set()
    for index, rule in enumerate(applicable):
        if rule.identity in handled:
            continue
        if index in exempting:
            text = _auditable_line(visible, linked_labels, rule)
        elif restored_hit:
            text = restored
        else:
            continue
        if rule.pattern.search(text) is not None:
            handled.add(rule.identity)
            found.append(rule)
    return found


def reported_retirements(
    line: str, source_path: Path, rules: Sequence[RetirementRule]
) -> list[RetirementRule]:
    """The rules this check would report if `line` stood in the doc at `source_path`."""
    occurrences = _occurrences(((1, line),), source_path, _RuleScan.build(rules))
    return [rule for rule, _, _ in occurrences.values()]


def link_retired_mentions(
    text: str, rules: Sequence[RetirementRule], record_path: Path, destination: str
) -> str:
    """`text` with each mention of a phrase the record at `record_path` retires linked to it.

    `destination` is the record's path as the doc that will hold `text` writes it. A mention
    inside a code span links the whole span, so the code span stays in one piece, and a mention
    is linked only when this check would then read the link as a citation of that phrase: a
    span longer than the phrase, or a mention inside another link, is left as it stands for
    `reported_retirements` to report. The tombstones of any other record are not touched.
    """
    cited = record_path.as_posix()
    for rule in rules:
        if rule.owner.path != record_path:
            continue
        link_like = [m.span() for pattern in _LINK_LIKE_RES for m in pattern.finditer(text)]
        code_spans = [m.span() for m in _CODE_SPAN_RE.finditer(text)]
        spans: list[tuple[int, int]] = []
        for match in rule.pattern.finditer(text):
            start, end = match.span()
            for code_start, code_end in code_spans:
                if code_start <= start and end <= code_end:
                    start, end = code_start, code_end
                    break
            if any(start < hi and lo < end for lo, hi in link_like):
                continue
            if _cites(text[start:end], cited, rule):
                spans.append((start, end))
        for start, end in reversed(spans):
            text = f"{text[:start]}[{text[start:end]}]({destination}){text[end:]}"
    return text


def retirement_registry(
    graph: DocGraph,
) -> tuple[list[RetirementRule], list[Finding]]:
    candidates: list[RetirementRule] = []
    findings: list[Finding] = []
    live_cli_identities: set[str] | None = None
    for node in sorted(graph.nodes.values(), key=lambda item: item.path.as_posix()):
        if not node.frontmatter.retires:
            continue
        if not _is_authoritative_owner(node, graph.config):
            findings.append(
                Finding(
                    check=RetiredReferencesCheck.name,
                    code=CODE_INACTIVE_RETIREMENT,
                    severity=Severity.error,
                    message=(
                        f"retirement declarations on '{node.id}' are inactive because "
                        "their owner is not a stable ADR"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="Move the declarations to the stable ADR that approved the retirement",
                    data={
                        "reason": "owner-not-stable-adr",
                    },
                )
            )
            continue
        for entry in node.frontmatter.retires:
            if entry.kind == RetirementKindEnum.cli_command:
                if live_cli_identities is None:
                    live_cli_identities = {item.identity for item in graph.source.surface("cli")}
                assert entry.surface_identity is not None
                if entry.surface_identity in live_cli_identities:
                    findings.append(
                        Finding(
                            check=RetiredReferencesCheck.name,
                            code=CODE_RETIREMENT_STILL_LIVE,
                            severity=Severity.error,
                            message=(
                                f"retired CLI identity '{entry.surface_identity}' is present "
                                "in the current derived surface"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion=(
                                "the tombstone and the code disagree: retire the tombstone "
                                "in a new decision record if the command was restored on "
                                "purpose, or raise the live command with its owner"
                            ),
                            data={
                                "kind": entry.kind.value,
                                "retirement-id": entry.id,
                                "surface-identity": entry.surface_identity,
                            },
                        )
                    )
                    continue
            for phrase in entry.matches:
                candidates.append(_retirement_rule(node, entry, phrase))

    by_phrase: dict[tuple[RetirementKindEnum, str], list[RetirementRule]] = {}
    for rule in candidates:
        key = (rule.entry.kind, _dedup_phrase_key(rule.phrase, rule.entry.kind))
        by_phrase.setdefault(key, []).append(rule)

    active: list[RetirementRule] = []
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
                    severity=Severity.error,
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


def _is_authoritative_owner(node: DocNode, config: IrminsulConfig | None) -> bool:
    return is_decision(node, config) and node.frontmatter.status == StatusEnum.stable


def _folds_case(phrase: str, kind: RetirementKindEnum) -> bool:
    """Whether this phrase is matched case-insensitively.

    Only `concept` phrases ever fold case, and only the ones written entirely
    in lower case — the "smart case" rule that `rg` and `vim` use. A concept is
    prose, so `legacy mode` has to catch `Legacy Mode` at the start of a
    sentence or inside a heading. But a concept named with a capital is a proper
    name, and folding its case would turn short ones into landmines: a two-token
    `Mode A` would match the ordinary English "whatever mode a project picks"
    and fail the build on prose that never mentions the retired thing. Word
    boundaries do not help — "mode a" is a whole-token match there. Case is the
    signal that separates the name from the words it is spelled with, so a
    capitalised declaration keeps it.

    The cost is that a capitalised phrase does not catch an all-lowercase
    reference to it. That is the right trade: guidance that names a retired
    concept spells it the way the tombstone declares it, and a tombstone that
    wants both spellings can list both in `matches:`.
    """
    if kind != RetirementKindEnum.concept:
        return False
    return not any(char.isupper() for char in phrase)


def _phrase_core(phrase: str) -> str:
    return r"\s+".join(re.escape(part) for part in phrase.split())


def _retirement_rule(owner: DocNode, entry: RetirementEntry, phrase: str) -> RetirementRule:
    folds_case = _folds_case(phrase, entry.kind)
    label = _citation_label(phrase)
    owner_path = owner.path.as_posix()
    return RetirementRule(
        owner=owner,
        entry=entry,
        phrase=phrase,
        pattern=re.compile(
            rf"(?<![\w-]){_phrase_core(phrase)}(?![\w-])", re.IGNORECASE if folds_case else 0
        ),
        folds_case=folds_case,
        owner_path=owner_path,
        expected_label=label.casefold() if folds_case else label,
        identity=(owner_path, entry.id),
    )


def _dedup_phrase_key(phrase: str, kind: RetirementKindEnum) -> str:
    """The key two declarations must share to count as the same retirement.

    Every concept phrase folds case here — including the capitalised ones that
    *match* case-sensitively. The registry's question is not "would these
    patterns fire on the same line" but "do two ADRs claim the same retired
    thing": `docs-only topology` and `Docs-Only Topology` name one concept,
    and keying them apart would let both rules run, so one guidance line would
    draw two errors and `ambiguous-retirement` would never fire. The
    smart-case *matching* semantics are separate — `_folds_case` decides how
    each surviving pattern compiles.
    """
    normalized = " ".join(phrase.split())
    return normalized.casefold() if kind == RetirementKindEnum.concept else normalized


def _guidance_sources(graph: DocGraph) -> list[_GuidanceSource]:
    assert graph.repo_root is not None
    assert graph.config is not None

    sources: list[_GuidanceSource] = []
    for node in sorted(graph.nodes.values(), key=lambda item: item.path.as_posix()):
        if not carries_certain_findings(node):
            continue
        # RFCs are frozen historical records and are never edited,
        # so auditing them would report findings nobody is allowed to fix.
        # ADRs are audited: they are current decisions, and the one that owns a
        # tombstone is exempted from it in `_RuleScan.applicable_to` rather than wholesale here.
        if is_rfc(node, graph.config):
            continue
        lines, unmatched = _file_lines(graph.repo_root / node.path, blank_generated=False)
        sources.append(
            _GuidanceSource(
                path=node.path,
                doc_id=node.id,
                lines=_blank_frontmatter_data(lines),
                unmatched_marker_line=unmatched,
            )
        )

    manifest = _repo_relative(graph.repo_root, manifest_rel_path(graph.config))
    # The agent guides are the highest-traffic guidance in the repo — `irminsul
    # init` tells every user to point their agent at them — and none of them is
    # a graph node.
    for guidance in graph.guidance_files:
        relative = Path(guidance.display)
        lines, unmatched = _numbered_lines(
            guidance.text or "", blank_generated=relative == manifest
        )
        sources.append(
            _GuidanceSource(
                path=relative,
                doc_id=None,
                lines=lines,
                unmatched_marker_line=unmatched,
                unreadable=guidance.unreadable,
            )
        )
    return sources


_PROSE_FRONTMATTER_KEYS = frozenset({"title", "summary"})
_TOP_LEVEL_KEY_RE = re.compile(r"([A-Za-z_][\w-]*)\s*:")


def _blank_frontmatter_data(
    lines: tuple[tuple[int, str], ...],
) -> tuple[tuple[int, str], ...]:
    """The lines with every frontmatter key but `title:` and `summary:` blanked.

    Those two are prose a reader browses; the rest is data. Another record's `retires:`
    block in particular names what that record retired, and its `matches:` and `guidance:`
    text quoting a phrase some other tombstone retired is not guidance presenting it as
    live. Line numbers are kept.
    """
    if not lines or not is_frontmatter_delimiter(lines[0][1]):
        return lines
    out = [lines[0]]
    keep = False
    for index, (lineno, line) in enumerate(lines[1:], start=1):
        if is_frontmatter_delimiter(line):
            return (*out, *lines[index:])
        if line[:1].strip():
            key = _TOP_LEVEL_KEY_RE.match(line)
            keep = key is not None and key.group(1) in _PROSE_FRONTMATTER_KEYS
        out.append((lineno, line if keep else ""))
    return lines


def _repo_relative(repo_root: Path, path: Path) -> Path:
    try:
        return path.relative_to(repo_root)
    except ValueError:
        return path


def _file_lines(
    path: Path, *, blank_generated: bool
) -> tuple[tuple[tuple[int, str], ...], int | None]:
    """Every line of the file, numbered, with the agent manifest's
    machine-generated region blanked and the line number of an unmatched
    generated-start marker.

    A graph node's frontmatter data is blanked afterwards by `_blank_frontmatter_data`.

    The manifest's generated region is not. It is derived output whose rows are the
    titles of the documents it indexes — including sealed RFCs, whose titles
    cannot change — so a finding there names a line no one may edit and that
    `irminsul fix` would rewrite identically. Line numbers are preserved so every other line in
    the file still reports accurately.

    Only the manifest carries that region, so only the manifest is read for its
    markers. Anywhere else the marker text is an example — the checks guide
    discusses it — and reading an example as a region would either fail
    the build on it or let a fenced pair hide stale guidance from a hard check.
    Which markers make a region is `find_region`'s rule, shared with every other reader of the
    manifest.

    Markers that do not make one region blank nothing, so a stray start marker — a
    bad merge, a half-written manifest — cannot switch a hard check off for the rest
    of the file. A start marker with no end marker at all is still reported: its line
    number comes back with the lines.

    A file that will not open or will not decode has no lines here, as `code-references`,
    `links` and `ignore-comments` treat the same guidance files. Raising instead would end
    `irminsul check` in a traceback for a `docs/AGENTS.md` saved as UTF-16 by an editor,
    and `agents-manifest/manifest-unreadable` — the finding whose explanation says how to
    repair that very file — would never print.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return (), None
    return _numbered_lines(text, blank_generated=blank_generated)


def _numbered_lines(
    text: str, *, blank_generated: bool
) -> tuple[tuple[tuple[int, str], ...], int | None]:
    lines = text.splitlines()
    if not blank_generated:
        return tuple(enumerate(lines, start=1)), None

    generated = range(0)
    unclosed: int | None = None
    try:
        region = find_region(text, GENERATED_START, GENERATED_END)
    except MalformedRegion as exc:
        if exc.ends == 0:
            unclosed = exc.line + 1
    else:
        if region is not None:
            generated = range(region.start_line, region.end_line + 1)
    out = tuple((index + 1, "" if index in generated else line) for index, line in enumerate(lines))
    return out, unclosed


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
    resolved = resolve_href(source_path.as_posix(), split.path.replace("\\", "/"), None)
    return None if resolved is None else resolved.as_posix()


def _reference_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def _citation_label(label: str) -> str:
    without_markup = _MARKUP_RE.sub("", label.replace("\\", ""))
    return " ".join(without_markup.split())


def _auditable_line(
    visible: str,
    linked_labels: list[_LinkedLabel],
    rule: RetirementRule,
) -> str:
    for linked in linked_labels:
        replacement = "" if _cites(linked.label, linked.destination, rule) else linked.label
        visible = visible.replace(linked.token, replacement)
    return visible


def _cites(label: str, destination: str, rule: RetirementRule) -> bool:
    """Whether a link with this label and resolved destination is a citation of the rule."""
    actual = _citation_label(label)
    if rule.folds_case:
        actual = actual.casefold()
    return actual == rule.expected_label and destination == rule.owner_path


def _unreadable_guidance_finding(source: _GuidanceSource) -> Finding:
    return Finding(
        check=RetiredReferencesCheck.name,
        code=CODE_GUIDANCE_UNREADABLE,
        # Certain for the same reason the unmatched marker is: the effect is that a hard
        # check read none of this file, and a suppression nobody declared has to fail.
        severity=Severity.error,
        message=(
            f"guidance file cannot be read as UTF-8, so nothing audited it: {source.unreadable}"
        ),
        path=source.path,
        doc_id=source.doc_id,
        suggestion=(
            "save the file as UTF-8, or remove it from `paths.extra_docs` — its links, code "
            "references and ignore comments are unchecked while it cannot be read"
        ),
    )


def _unmatched_marker_finding(source: _GuidanceSource) -> Finding:
    return Finding(
        check=RetiredReferencesCheck.name,
        code=CODE_UNMATCHED_GENERATED_MARKER,
        # An error because the retired-reference findings it causes, in the generated rows
        # audited as prose until the region closes, are errors.
        severity=Severity.error,
        message="generated-region start marker has no matching end marker",
        path=source.path,
        doc_id=source.doc_id,
        line=source.unmatched_marker_line,
        suggestion=(
            f"Close the region with `{GENERATED_END}`, or remove the start marker — "
            "until then the generated rows below it are audited as prose"
        ),
        data={
            "marker": GENERATED_START,
        },
    )


def _retired_reference_finding(
    source: _GuidanceSource,
    lineno: int,
    rule: RetirementRule,
    occurrences: int,
) -> Finding:
    return Finding(
        check=RetiredReferencesCheck.name,
        code=CODE_RETIRED_REFERENCE,
        # An error, not a warning: this audit is what makes stale guidance
        # fail, and CI does not fail on hints.
        severity=Severity.error,
        message=(f"current guidance references retired {rule.entry.kind.value} '{rule.phrase}'"),
        path=source.path,
        doc_id=source.doc_id,
        line=lineno,
        suggestion=(
            f"{rule.entry.guidance} For historical discussion, link the exact phrase "
            f"to {rule.owner.path.as_posix()}"
        ),
        data={
            "kind": rule.entry.kind.value,
            "match": rule.phrase,
            "retirement-id": rule.entry.id,
            "declared-by": rule.owner.path.as_posix(),
            "guidance": rule.entry.guidance,
            "occurrences": str(occurrences),
        },
    )
