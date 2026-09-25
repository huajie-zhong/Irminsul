"""Deterministic doc-reality audits."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity, carries_certain_findings
from irminsul.checks.globs import (
    is_external_source_location,
    is_source_path,
    resolve_display_path,
    source_root_prefixes,
)
from irminsul.config import TerminologyRule, in_layer
from irminsul.docgraph import DocGraph, DocNode, is_rfc
from irminsul.fences import FenceTracker
from irminsul.frontmatter import ClaimStateEnum, StatusEnum
from irminsul.git.mtime import last_commit_time_any_repo
from irminsul.regen.agents_md import (
    GENERATED_END,
    GENERATED_START,
    manifest_rel_path,
    render_generated_section,
)

_LOCAL_MD_RE = re.compile(r"(?<![\w.-])((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.md)(?![\w.-])")
# A label may hold an escaped bracket, which `irminsul new` writes for a title that
# contains one; treating that as the end of the label read a valid link as prose.
_LABEL = r"(?:\\.|[^\]\n\\])*"
_MARKDOWN_LINK_RE = re.compile(rf"!?\[{_LABEL}\](?:\([^\)\n]*\)|\[{_LABEL}\])")
_LINK_DEFINITION_RE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s+\S+")
_IGNORE_RE = re.compile(r"irminsul:ignore\s+prose-file-reference")
_IGNORE_START_RE = re.compile(r"irminsul:ignore-start\s+prose-file-reference")
_IGNORE_END_RE = re.compile(r"irminsul:ignore-end\s+prose-file-reference")
_CLAIM_REF_RE = re.compile(r"claim:([A-Za-z0-9_.-]+)")
_RISKY_CLAIM_RE = re.compile(
    r"\b("
    r"CI automatically|blocks?|guarantees?|rewrites?|generated daily|nightly|"
    r"auto-updates?|enforces?|cannot merge|fails? the build|PR is blocked|"
    r"Fail the PR|no PR can merge|auto-generated daily"
    r")\b",
    re.IGNORECASE,
)
_STRUCTURED_SECTION_HEADINGS = {
    "mechanical enforcement",
    "ci pipeline",
    "supersession enforcement",
    "health dashboard",
}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_EVIDENCE_SPELLING_SUGGESTION = (
    "Spell evidence the way `describes:` does: repo-relative inside the docs repo, "
    "source-root-relative for files under a source root outside it"
)


def _stable_audit_nodes(graph: DocGraph) -> list[DocNode]:
    return [node for node in graph.nodes.values() if node.frontmatter.status == StatusEnum.stable]


def _certain_audit_nodes(graph: DocGraph) -> list[DocNode]:
    return [node for node in graph.nodes.values() if carries_certain_findings(node)]


def _is_protected_claim_node(node: DocNode, graph: DocGraph) -> bool:
    if graph.config is None:
        return False
    return in_layer(graph.config, node.path, "foundation") or in_layer(
        graph.config, node.path, "architecture"
    )


def _line_link_spans(line: str) -> list[range]:
    if _LINK_DEFINITION_RE.match(line):
        return [range(0, len(line))]
    return [range(match.start(), match.end()) for match in _MARKDOWN_LINK_RE.finditer(line)]


def _inside_any(pos: int, spans: list[range]) -> bool:
    return any(pos in span for span in spans)


def _first_unlinked_local_md(line: str) -> str | None:
    link_spans = _line_link_spans(line)
    for match in _LOCAL_MD_RE.finditer(line):
        if not _inside_any(match.start(), link_spans):
            return match.group(1)
    return None


def _without_ignore_comment(line: str, marker: re.Match[str]) -> str:
    comment_start = line.rfind("<!--", 0, marker.start())
    comment_end = line.find("-->", marker.end())
    if (
        comment_start != -1
        and comment_end != -1
        and "-->" not in line[comment_start : marker.start()]
        and "<!--" not in line[marker.end() : comment_end]
    ):
        return line[:comment_start] + line[comment_end + 3 :]
    return line[: marker.start()] + line[marker.end() :]


def _docs_root(graph: DocGraph) -> str:
    assert graph.config is not None
    return graph.config.paths.docs_root.strip("/\\")


def _claim_refs(text: str) -> set[str]:
    return {match.group(1) for match in _CLAIM_REF_RE.finditer(text)}


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_DOC_LINK_RE = re.compile(rf"!?\[{_LABEL}\]\((?:[^)\s#]*\.md)?(?:#[^)\s]*)?\)")


def _asserted_prose(text: str) -> str:
    """`text` without the markup a risky word can sit in without being asserted.

    A comment, a code span, and a link target are not prose, and the label of a link to a
    doc names that doc: "[Finding classes decide what blocks](...)" claims nothing blocks.
    """
    masked = _DOC_LINK_RE.sub(" ", _HTML_COMMENT_RE.sub(" ", text))
    for pattern in (_INLINE_CODE_RE, _LINK_DEST_RE, _AUTOLINK_RE):
        masked = pattern.sub(" ", masked)
    return masked


@dataclass(frozen=True)
class _BodyParagraph:
    start_line: int
    text: str


@dataclass(frozen=True)
class _BodySection:
    start_line: int
    heading: str
    text: str


def _body_paragraphs(body: str) -> list[_BodyParagraph]:
    paragraphs: list[_BodyParagraph] = []
    current: list[str] = []
    start_line: int | None = None
    fence = FenceTracker()

    def flush() -> None:
        nonlocal current, start_line
        if current and start_line is not None:
            paragraphs.append(_BodyParagraph(start_line=start_line, text="\n".join(current)))
        current = []
        start_line = None

    for lineno, line in enumerate(body.splitlines(), start=1):
        if fence.consume(line):
            flush()
            continue
        if not line.strip():
            flush()
            continue
        if start_line is None:
            start_line = lineno
        current.append(line)
    flush()
    return paragraphs


def _body_sections(body: str) -> list[_BodySection]:
    """One section per heading, running to the next heading at the same or a higher level.

    A section holds its subsections, and each subsection is also a section of its own, so a
    structured heading nested under the doc's title is read instead of swallowed by it.
    """
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []
    fence = FenceTracker()
    for index, line in enumerate(lines):
        if fence.consume(line):
            continue
        match = _HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))

    sections: list[_BodySection] = []
    for position, (index, level, heading) in enumerate(headings):
        end = next(
            (later for later, later_level, _ in headings[position + 1 :] if later_level <= level),
            len(lines),
        )
        sections.append(
            _BodySection(
                start_line=index + 1,
                heading=heading,
                text="\n".join(lines[index + 1 : end]),
            )
        )
    return sections


def _normalize_heading(heading: str) -> str:
    normalized = re.sub(r"\s+", " ", heading).strip().lower()
    # A trailing parenthetical qualifies a heading rather than renaming it.
    normalized = re.sub(r"\s*\([^()]*\)$", "", normalized)
    if normalized.startswith("the "):
        normalized = normalized[4:]
    return normalized


CODE_UNLINKED_REFERENCE = "prose-file-reference/unlinked-reference"
CODE_IGNORE_END_WITHOUT_START = "prose-file-reference/ignore-end-without-start"
CODE_IGNORE_START_WITHOUT_END = "prose-file-reference/ignore-start-without-end"
CODE_STALE_SUPPRESSION = "prose-file-reference/stale-suppression"


class ProseFileReferenceCheck:
    """Local Markdown files named in prose must be real links, not bare mentions."""

    name: ClassVar[str] = "prose-file-reference"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNLINKED_REFERENCE: (
            "A local `.md` filename is named in prose without a Markdown link. Convert it "
            "to a link, or suppress the line with an `irminsul:ignore prose-file-reference` "
            "comment if it's intentionally a bare mention."
        ),
        CODE_IGNORE_END_WITHOUT_START: (
            "An `irminsul:ignore-end prose-file-reference` marker has no matching "
            "ignore-start. Remove it or add the matching start marker."
        ),
        CODE_IGNORE_START_WITHOUT_END: (
            "An `irminsul:ignore-start prose-file-reference` marker is never closed. Add "
            "the matching `irminsul:ignore-end prose-file-reference` marker."
        ),
        CODE_STALE_SUPPRESSION: (
            "An ignore marker no longer hides an unlinked local Markdown reference — the "
            "prose it was protecting has since changed. Remove the stale suppression."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNLINKED_REFERENCE: FindingClass.certain,
        CODE_IGNORE_END_WITHOUT_START: FindingClass.certain,
        CODE_IGNORE_START_WITHOUT_END: FindingClass.certain,
        CODE_STALE_SUPPRESSION: FindingClass.certain,
    }
    #: Findings about this check's own suppression markers. A baseline must never hide
    #: one: an unclosed `ignore-start` silences the rest of the doc, so baselining it
    #: buries both the broken marker and everything it goes on to swallow.
    audits_suppression: ClassVar[frozenset[str]] = frozenset(
        {CODE_IGNORE_END_WITHOUT_START, CODE_IGNORE_START_WITHOUT_END, CODE_STALE_SUPPRESSION}
    )

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for node in _certain_audit_nodes(graph):
            if is_rfc(node, graph.config):
                continue

            fence = FenceTracker()
            in_ignore_block = False
            ignore_block_start: int | None = None
            ignore_block_used = False
            for lineno, line in enumerate(node.body.splitlines(), start=1):
                if fence.consume(line):
                    continue
                if _IGNORE_START_RE.search(line):
                    in_ignore_block = True
                    ignore_block_start = lineno
                    ignore_block_used = False
                    if _IGNORE_END_RE.search(line):
                        out.append(_stale_suppression(node, lineno, scope="block"))
                        in_ignore_block = False
                        ignore_block_start = None
                    continue
                if _IGNORE_END_RE.search(line):
                    if not in_ignore_block:
                        out.append(
                            Finding(
                                check=self.name,
                                code=CODE_IGNORE_END_WITHOUT_START,
                                severity=Severity.error,
                                message="ignore-end without matching ignore-start",
                                path=node.path,
                                doc_id=node.id,
                                line=node.file_line(lineno),
                                suggestion=(
                                    "Remove the unmatched ignore-end marker or add a matching "
                                    "ignore-start marker"
                                ),
                            )
                        )
                    elif not ignore_block_used and ignore_block_start is not None:
                        out.append(_stale_suppression(node, ignore_block_start, scope="block"))
                    in_ignore_block = False
                    ignore_block_start = None
                    ignore_block_used = False
                    continue
                if in_ignore_block:
                    ignore_match = _IGNORE_RE.search(line)
                    content_line = (
                        _without_ignore_comment(line, ignore_match)
                        if ignore_match is not None
                        else line
                    )
                    if _first_unlinked_local_md(content_line) is not None:
                        ignore_block_used = True
                    continue

                ignore_match = _IGNORE_RE.search(line)
                if ignore_match is not None:
                    unsuppressed_line = _without_ignore_comment(line, ignore_match)
                    if _first_unlinked_local_md(unsuppressed_line) is None:
                        out.append(_stale_suppression(node, lineno, scope="line"))
                    continue

                target = _first_unlinked_local_md(line)
                if target is not None:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNLINKED_REFERENCE,
                            severity=Severity.error,
                            message=(f"local markdown reference '{target}' is not a Markdown link"),
                            path=node.path,
                            doc_id=node.id,
                            line=node.file_line(lineno),
                            suggestion=(
                                "Convert it to a Markdown link or add "
                                "`<!-- irminsul:ignore prose-file-reference "
                                'reason="..." -->` on the line'
                            ),
                        )
                    )
            if in_ignore_block and ignore_block_start is not None:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_IGNORE_START_WITHOUT_END,
                        severity=Severity.error,
                        message="ignore-start without matching ignore-end",
                        path=node.path,
                        doc_id=node.id,
                        line=node.file_line(ignore_block_start),
                        suggestion="Add `<!-- irminsul:ignore-end prose-file-reference -->`",
                    )
                )

        return out


def _stale_suppression(
    node: DocNode,
    line: int,
    *,
    scope: str,
) -> Finding:
    return Finding(
        check=ProseFileReferenceCheck.name,
        code=CODE_STALE_SUPPRESSION,
        severity=Severity.error,
        category="stale-suppression",
        message=(f"{scope} suppression no longer hides an unlinked local Markdown reference"),
        path=node.path,
        doc_id=node.id,
        line=node.file_line(line),
        suggestion="Remove the stale prose-file-reference suppression marker",
        data={"problem": "stale-suppression", "scope": scope},
    )


CODE_EVIDENCE_NOT_REPO_RELATIVE = "claim-provenance/evidence-not-repo-relative"
CODE_EVIDENCE_PATH_MISSING = "claim-provenance/evidence-path-missing"
CODE_EVIDENCE_STATE_MISMATCH = "claim-provenance/evidence-state-mismatch"
CODE_UNKNOWN_CLAIM_REF = "claim-provenance/unknown-claim-ref"
CODE_RISKY_PROSE_UNCLAIMED = "claim-provenance/risky-prose-unclaimed"
CODE_STRUCTURED_SECTION_UNCLAIMED = "claim-provenance/structured-section-unclaimed"
CODE_EVIDENCE_DRIFT = "claim-provenance/evidence-drift"
CODE_PLANNED_CLAIM_RESOLVED = "claim-provenance/planned-claim-resolved"
CODE_NEGATED_CLAIM = "claim-provenance/negated-claim"
_NEGATION_RE = re.compile(r"\b(?:no|not|never|none)\b", re.IGNORECASE)
_PRESENCE_STATES = {ClaimStateEnum.implemented, ClaimStateEnum.available, ClaimStateEnum.enabled}


class ClaimProvenanceCheck:
    """High-risk assertions need structured claims backed by evidence that fits their state."""

    name: ClassVar[str] = "claim-provenance"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_EVIDENCE_NOT_REPO_RELATIVE: (
            "A claim's evidence path is absolute. Evidence must be a repo-relative path."
        ),
        CODE_EVIDENCE_PATH_MISSING: (
            "A claim's evidence path does not exist in the repo. Point it at existing "
            "source, config, CI, or doc evidence."
        ),
        CODE_EVIDENCE_STATE_MISMATCH: (
            "A claim has no evidence appropriate for its declared state (planned, "
            "implemented, available, enabled, external). Add evidence of the right kind, "
            "or change the claim's state."
        ),
        CODE_UNKNOWN_CLAIM_REF: (
            "A `claim:<id>` marker in the doc body references an id not declared in "
            "frontmatter. Add the matching frontmatter claim or remove the marker."
        ),
        CODE_RISKY_PROSE_UNCLAIMED: (
            "A paragraph makes a high-risk enforcement/automation claim (blocks, "
            "guarantees, auto-generates, ...) without a structured `claim:<id>` "
            "reference. Words in a comment, a code span, a link target, or the label of a "
            "link to a doc are not read. Add a frontmatter claim and reference it; the "
            "marker says which claim the paragraph rests on, not that the claim supports it."
        ),
        CODE_STRUCTURED_SECTION_UNCLAIMED: (
            "A structured section (e.g. 'Mechanical Enforcement') has no `claim:<id>` "
            "marker backing its assertions. Add at least one relevant claim reference."
        ),
        CODE_EVIDENCE_DRIFT: (
            "A claim's evidence changed after the doc was last committed. Review whether "
            "the claim is still true and update the doc."
        ),
        CODE_PLANNED_CLAIM_RESOLVED: (
            "A 'planned' claim cites an RFC that has since reached a resolved state. "
            "Update the claim's state to match reality, or reword/remove it."
        ),
        CODE_NEGATED_CLAIM: (
            "A claim's text denies something while its state asserts presence "
            "(implemented, available, or enabled), so the evidence is checked against the "
            "opposite of what the sentence says. Restate the claim as the positive fact "
            "its evidence supports."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_EVIDENCE_NOT_REPO_RELATIVE: FindingClass.certain,
        CODE_EVIDENCE_PATH_MISSING: FindingClass.certain,
        CODE_EVIDENCE_STATE_MISMATCH: FindingClass.certain,
        CODE_UNKNOWN_CLAIM_REF: FindingClass.certain,
        CODE_RISKY_PROSE_UNCLAIMED: FindingClass.hint,
        CODE_STRUCTURED_SECTION_UNCLAIMED: FindingClass.hint,
        CODE_EVIDENCE_DRIFT: FindingClass.hint,
        CODE_PLANNED_CLAIM_RESOLVED: FindingClass.certain,
        CODE_NEGATED_CLAIM: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        out: list[Finding] = []
        for node in _certain_audit_nodes(graph):
            claim_ids = {claim.id for claim in node.frontmatter.claims}
            # Only the foundation and architecture layers are asked for claims. A claim
            # written anywhere else still has to cite evidence that exists and fits its
            # state, and a marker naming no claim is a broken reference wherever it is.
            resolved = self._resolve_node_evidence(graph, node)
            out.extend(self._validate_evidence(graph, node, resolved))
            out.extend(self._validate_body_claim_refs(node, claim_ids))
            if not _is_protected_claim_node(node, graph):
                continue

            # The hints ask whether finished prose is backed by a claim, which a draft
            # cannot answer yet. The certain codes above and the planned-claim one below
            # report a reference that is already wrong, whatever the doc's status.
            advisory = node.frontmatter.status == StatusEnum.stable
            if advisory:
                out.extend(self._scan_risky_prose(node, claim_ids))
                out.extend(self._scan_structured_sections(node, claim_ids))
                out.extend(self._scan_evidence_drift(graph, node, resolved))
            out.extend(self._scan_planned_claim_lifecycle(graph, node))
            if advisory:
                out.extend(self._scan_negated_claims(node))

        return out

    def _scan_negated_claims(self, node: DocNode) -> list[Finding]:
        return [
            Finding(
                check=self.name,
                code=CODE_NEGATED_CLAIM,
                severity=Severity.info,
                message=(
                    f"claim '{claim.id}' is worded as a negation but declares "
                    f"state '{claim.state.value}'"
                ),
                path=node.path,
                doc_id=node.id,
                suggestion="Restate the claim as the positive fact its evidence supports",
                data={"problem": "negated-claim", "claim": claim.id},
            )
            for claim in node.frontmatter.claims
            if claim.state in _PRESENCE_STATES and _NEGATION_RE.search(claim.claim)
        ]

    def _resolve_evidence(self, graph: DocGraph, evidence: str) -> Path | None:
        assert graph.config is not None
        assert graph.repo_root is not None
        return resolve_display_path(graph.repo_root, graph.config.paths.source_roots, evidence)

    def _resolve_node_evidence(self, graph: DocGraph, node: DocNode) -> dict[str, Path | None]:
        """Every evidence spelling of the node, resolved once.

        `_validate_evidence`, `_scan_evidence_drift`, and the source
        classifiers all need the same answer; resolving here keeps it to one
        disk probe per spelling instead of up to three per scan.
        """
        return {
            evidence: self._resolve_evidence(graph, evidence)
            for claim in node.frontmatter.claims
            for evidence in claim.evidence
        }

    def _validate_evidence(
        self, graph: DocGraph, node: DocNode, resolved: dict[str, Path | None]
    ) -> list[Finding]:
        assert graph.config is not None
        assert graph.repo_root is not None

        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            evidence_refs = [
                (Path(evidence), resolved.get(evidence)) for evidence in claim.evidence
            ]
            for evidence, (rel_path, resolved_path) in zip(
                claim.evidence, evidence_refs, strict=True
            ):
                if rel_path.is_absolute() or ".." in rel_path.parts:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_EVIDENCE_NOT_REPO_RELATIVE,
                            severity=Severity.error,
                            message=(
                                f"claim '{claim.id}' evidence must not be absolute or "
                                f"escape the tree with '..': '{evidence}'"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion=_EVIDENCE_SPELLING_SUGGESTION,
                        )
                    )
                    continue
                if resolved_path is None:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_EVIDENCE_PATH_MISSING,
                            severity=Severity.error,
                            message=f"claim '{claim.id}' evidence path does not exist: '{evidence}'",
                            path=node.path,
                            doc_id=node.id,
                            suggestion=(
                                "Point the claim at existing source, config, CI, or doc "
                                f"evidence. {_EVIDENCE_SPELLING_SUGGESTION}"
                            ),
                        )
                    )

            if not self._has_state_appropriate_evidence(graph, claim.state, evidence_refs):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_EVIDENCE_STATE_MISMATCH,
                        severity=Severity.error,
                        message=(
                            f"claim '{claim.id}' has no evidence appropriate for "
                            f"state '{claim.state.value}'"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=self._state_suggestion(claim.state),
                    )
                )
        return out

    def _has_state_appropriate_evidence(
        self,
        graph: DocGraph,
        state: ClaimStateEnum,
        evidence_refs: list[tuple[Path, Path | None]],
    ) -> bool:
        if state == ClaimStateEnum.planned:
            return any(self._is_rfc_evidence(graph, path) for path, _ in evidence_refs)
        if state == ClaimStateEnum.implemented:
            return any(
                self._is_implementation_evidence(graph, path, resolved)
                for path, resolved in evidence_refs
            )
        if state == ClaimStateEnum.available:
            return any(
                self._is_implementation_evidence(graph, path, resolved)
                for path, resolved in evidence_refs
            ) and any(self._is_enablement_doc_evidence(graph, path) for path, _ in evidence_refs)
        if state == ClaimStateEnum.enabled:
            return any(self._is_enabled_evidence(path) for path, _ in evidence_refs)
        if state == ClaimStateEnum.external:
            return any(
                self._is_external_process_evidence(graph, path, resolved)
                for path, resolved in evidence_refs
            )
        return False

    def _state_suggestion(self, state: ClaimStateEnum) -> str:
        suggestions = {
            ClaimStateEnum.planned: "Add an RFC evidence path under the rfcs layer",
            ClaimStateEnum.implemented: "Add source or component-doc implementation evidence",
            ClaimStateEnum.available: "Add implementation evidence plus user-facing enablement docs",
            ClaimStateEnum.enabled: "Add irminsul.toml, action.yml, or .github/workflows evidence",
            ClaimStateEnum.external: "Add process, operation, external-tool, or config documentation",
        }
        return suggestions[state]

    def _validate_body_claim_refs(self, node: DocNode, claim_ids: set[str]) -> list[Finding]:
        out: list[Finding] = []
        fence = FenceTracker()
        for lineno, line in enumerate(node.body.splitlines(), start=1):
            if fence.consume(line):
                continue
            for match in _CLAIM_REF_RE.finditer(line):
                claim_id = match.group(1)
                if claim_id not in claim_ids:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNKNOWN_CLAIM_REF,
                            severity=Severity.error,
                            message=f"unknown structured claim reference: 'claim:{claim_id}'",
                            path=node.path,
                            doc_id=node.id,
                            line=node.file_line(lineno),
                            suggestion="Add a matching frontmatter claim or remove the marker",
                        )
                    )
        return out

    def _scan_risky_prose(self, node: DocNode, claim_ids: set[str]) -> list[Finding]:
        out: list[Finding] = []
        for paragraph in _body_paragraphs(node.body):
            if _RISKY_CLAIM_RE.search(_asserted_prose(paragraph.text)) is None:
                continue
            if any(claim_id in claim_ids for claim_id in _claim_refs(paragraph.text)):
                continue
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_RISKY_PROSE_UNCLAIMED,
                    severity=Severity.warning,
                    message="high-risk enforcement or automation prose lacks a structured claim reference",
                    path=node.path,
                    doc_id=node.id,
                    line=node.file_line(paragraph.start_line),
                    suggestion="Add a frontmatter claim and reference it with `claim:<id>`",
                )
            )
        return out

    def _scan_structured_sections(self, node: DocNode, claim_ids: set[str]) -> list[Finding]:
        out: list[Finding] = []
        for section in _body_sections(node.body):
            normalized_heading = _normalize_heading(section.heading)
            if normalized_heading not in _STRUCTURED_SECTION_HEADINGS:
                continue
            if any(claim_id in claim_ids for claim_id in _claim_refs(section.text)):
                continue
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_STRUCTURED_SECTION_UNCLAIMED,
                    severity=Severity.warning,
                    message=f"section '{section.heading}' needs a structured claim reference",
                    path=node.path,
                    doc_id=node.id,
                    line=node.file_line(section.start_line),
                    suggestion="Add at least one relevant `claim:<id>` marker in this section",
                )
            )
        return out

    def _scan_evidence_drift(
        self, graph: DocGraph, node: DocNode, resolved: dict[str, Path | None]
    ) -> list[Finding]:
        assert graph.repo_root is not None

        doc_time = last_commit_time_any_repo(graph.repo_root / node.path, graph.repo_root)
        if doc_time is None or doc_time.when is None:
            return []

        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            latest_path: str | None = None
            latest_time = None
            for evidence in claim.evidence:
                evidence_abs = resolved.get(evidence)
                if evidence_abs is None:
                    continue
                evidence_time = last_commit_time_any_repo(evidence_abs, graph.repo_root)
                if evidence_time is None or evidence_time.when is None:
                    continue
                if latest_time is None or evidence_time.when > latest_time:
                    latest_time = evidence_time.when
                    latest_path = evidence
            if latest_time is None or latest_time <= doc_time.when:
                continue
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_EVIDENCE_DRIFT,
                    severity=Severity.warning,
                    message=(
                        f"claim '{claim.id}' cites evidence changed after the doc: '{latest_path}'"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion="Review the claim and update the doc if the evidence changed its truth",
                )
            )
        return out

    def _scan_planned_claim_lifecycle(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        assert graph.repo_root is not None

        from irminsul.checks.rfc_follow_through import PLANNED_CLAIM_STALE_STATES

        resolved_states = PLANNED_CLAIM_STALE_STATES
        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            if claim.state != ClaimStateEnum.planned:
                continue
            for evidence in claim.evidence:
                evidence_path = Path(evidence)
                evidence_node = graph.by_path.get(evidence_path)
                if evidence_node is None or not self._is_rfc_evidence(graph, evidence_path):
                    continue
                rfc_state = evidence_node.frontmatter.rfc_state
                if rfc_state not in resolved_states:
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_PLANNED_CLAIM_RESOLVED,
                        severity=Severity.error,
                        message=(
                            f"planned claim '{claim.id}' cites resolved RFC "
                            f"'{evidence}' ({rfc_state.value})"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=(
                            "Update the claim to implemented, available, or enabled; "
                            "or remove/reword it if the RFC was not adopted"
                        ),
                    )
                )
        return out

    def _is_rfc_evidence(self, graph: DocGraph, path: Path) -> bool:
        assert graph.config is not None
        return in_layer(graph.config, path, "rfcs") and path.suffix == ".md"

    def _is_source_evidence(self, graph: DocGraph, path: Path, resolved: Path | None) -> bool:
        """True when the evidence spelling names a configured source tree.

        Two spellings, because the source walk emits two. Inside the docs repo
        a source file displays repo-relative, so the configured root is a
        literal prefix and the test stays lexical — a not-yet-created
        `src/new.py` still reads as source, and `_validate_evidence` reports
        its absence once rather than twice. Outside the docs repo (`siblings`)
        the display is source-root-relative and carries no prefix at all, so
        membership is settled on disk instead — on `resolved`, the caller's
        already-resolved location of the spelling, so nothing resolves twice.
        """
        assert graph.config is not None
        assert graph.repo_root is not None
        path_posix = path.as_posix()
        source_roots = graph.config.paths.source_roots
        for prefix in source_root_prefixes(graph.repo_root, source_roots):
            if not prefix:
                if self._is_repo_root_source(graph, path, path_posix):
                    return True
                continue
            if path_posix == prefix or path_posix.startswith(f"{prefix}/"):
                return True
        return is_external_source_location(graph.repo_root, source_roots, resolved)

    def _is_repo_root_source(self, graph: DocGraph, path: Path, path_posix: str) -> bool:
        """Whether a source root that *is* the repo root claims this path.

        `source_roots = ["."]` is what `irminsul init` writes for a flat Go
        repo, and its repo-relative prefix is the empty string, which every
        path starts with. Answering "yes, everything" there is wrong in the one
        direction that matters: the docs tree, `irminsul.toml`, the Action and
        the CI workflows sit under the repo root too, and each of them is the
        evidence some *other* claim state is defined by. `state: external` is
        "process evidence and not source", so an unconditional yes made every
        external claim unsatisfiable, and `implemented`/`available` stopped
        being checked at all.

        The exclusions are the ones the source walk and the sibling evidence
        classifiers already own — the docs tree, the enablement files, and the
        walk's dot-directory and bytecode exclusions — so the answer here
        matches the set of files the source walk actually returns for a
        repo-root source root.
        """
        docs_root = _docs_root(graph)
        if path_posix == docs_root or path_posix.startswith(f"{docs_root}/"):
            return False
        if self._is_enabled_evidence(path):
            return False
        return is_source_path(path_posix, [""])

    def _is_component_doc_evidence(self, graph: DocGraph, path: Path) -> bool:
        assert graph.config is not None
        return in_layer(graph.config, path, "components")

    def _is_implementation_evidence(
        self, graph: DocGraph, path: Path, resolved: Path | None
    ) -> bool:
        return self._is_source_evidence(graph, path, resolved) or self._is_component_doc_evidence(
            graph, path
        )

    def _is_enablement_doc_evidence(self, graph: DocGraph, path: Path) -> bool:
        path_posix = path.as_posix()
        docs_root = _docs_root(graph)
        assert graph.config is not None
        return (
            path_posix.startswith(f"{docs_root}/") and not in_layer(graph.config, path, "rfcs")
        ) or self._is_enabled_evidence(path)

    def _is_enabled_evidence(self, path: Path) -> bool:
        path_posix = path.as_posix()
        return (
            path_posix == "irminsul.toml"
            or path_posix in {"action.yml", "action.yaml"}
            or (path_posix.startswith(".github/workflows/") and path.suffix in {".yml", ".yaml"})
        )

    def _is_external_process_evidence(
        self, graph: DocGraph, path: Path, resolved: Path | None
    ) -> bool:
        path_posix = path.as_posix()
        docs_root = _docs_root(graph)
        return (
            path_posix.startswith(f"{docs_root}/")
            or path_posix == "irminsul.toml"
            or path_posix in {"action.yml", "action.yaml"}
            or path_posix in {".pre-commit-config.yaml", ".pre-commit-config.yml"}
            or path_posix.startswith(".github/")
        ) and not self._is_source_evidence(graph, path, resolved)


CODE_AMBIGUOUS_TERM = "terminology-overload/ambiguous-term"


class TerminologyOverloadCheck:
    """Configured overloaded terms must appear with an explicit disambiguating phrase."""

    name: ClassVar[str] = "terminology-overload"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_AMBIGUOUS_TERM: (
            "A configured overloaded term appears without one of its explicit "
            "disambiguating phrases. Use one of the configured explicit phrases, or "
            "reword to remove the ambiguity."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_AMBIGUOUS_TERM: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        out: list[Finding] = []
        rules = graph.config.checks.terminology_overload.rules
        for node in _stable_audit_nodes(graph):
            if is_rfc(node, graph.config):
                continue
            fence = FenceTracker()
            for lineno, line in enumerate(node.body.splitlines(), start=1):
                if fence.consume(line):
                    continue
                for rule in rules:
                    if not _line_has_term(line, rule.term):
                        continue
                    if _term_is_explicit(line, rule):
                        continue
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_AMBIGUOUS_TERM,
                            severity=self.default_severity,
                            message=f"'{rule.term}' is ambiguous here",
                            path=node.path,
                            doc_id=node.id,
                            line=node.file_line(lineno),
                            suggestion=rule.suggestion,
                        )
                    )
        return out


CODE_MANIFEST_MISSING = "agents-manifest/manifest-missing"
CODE_MANIFEST_UNREADABLE = "agents-manifest/manifest-unreadable"
CODE_MISSING_GENERATED_MARKERS = "agents-manifest/missing-generated-markers"
CODE_GENERATED_SECTION_DRIFT = "agents-manifest/generated-section-drift"
CODE_MISSING_REQUIRED_HEADING = "agents-manifest/missing-required-heading"


class AgentsManifestCheck:
    """The docs/AGENTS.md navigation manifest must exist where adopted and match regen output."""

    name: ClassVar[str] = "agents-manifest"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_MANIFEST_MISSING: (
            "The repo has opted into `agents-manifest` (it's listed in `checks.enabled`) but "
            "`docs/AGENTS.md` does not exist. Run `irminsul regen agents-md`."
        ),
        CODE_MANIFEST_UNREADABLE: (
            "`docs/AGENTS.md` exists but could not be read as UTF-8 — most often it was "
            "saved as UTF-16 by a Windows editor. Save it as UTF-8, or delete it and run "
            "`irminsul regen agents-md` to scaffold a fresh one."
        ),
        CODE_MISSING_GENERATED_MARKERS: (
            "The manifest is missing its generated-section start/end markers. Run "
            "`irminsul regen agents-md`."
        ),
        CODE_GENERATED_SECTION_DRIFT: (
            "The manifest's generated section no longer matches what the current doc "
            "graph would produce. Run `irminsul regen agents-md`."
        ),
        CODE_MISSING_REQUIRED_HEADING: (
            "The manifest is missing a required heading (Foundations or Protocol). Run "
            "`irminsul regen agents-md`, or add the section manually."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MANIFEST_MISSING: FindingClass.certain,
        CODE_MANIFEST_UNREADABLE: FindingClass.certain,
        CODE_MISSING_GENERATED_MARKERS: FindingClass.certain,
        CODE_GENERATED_SECTION_DRIFT: FindingClass.certain,
        CODE_MISSING_REQUIRED_HEADING: FindingClass.certain,
    }

    _REQUIRED_HEADINGS: ClassVar[tuple[str, ...]] = ("Foundations", "Protocol")

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None or graph.config is None:
            return []

        rel_path = manifest_rel_path(graph.config)
        abs_path = graph.repo_root / rel_path
        suggestion = "Run `irminsul regen agents-md`"

        if not abs_path.exists():
            # The check ships opt-in: a missing manifest is only an error for
            # repos that have adopted it by listing the check in `checks.enabled`.
            # An existing manifest is always validated, regardless of opt-in.
            if self.name not in graph.config.checks.enabled:
                return []
            return [
                Finding(
                    check=self.name,
                    code=CODE_MANIFEST_MISSING,
                    severity=Severity.error,
                    message=f"agent manifest '{rel_path.as_posix()}' is missing",
                    path=rel_path,
                    suggestion=suggestion,
                )
            ]

        try:
            text = abs_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError) as exc:
            # An exception here would abort the run and lose every other check's
            # findings to a traceback that names no file, so an unreadable manifest,
            # most often one saved as UTF-16, is reported as a finding of its own.
            return [
                Finding(
                    check=self.name,
                    code=CODE_MANIFEST_UNREADABLE,
                    severity=Severity.error,
                    message=(
                        f"agent manifest '{rel_path.as_posix()}' could not be read as "
                        f"UTF-8 ({type(exc).__name__})"
                    ),
                    path=rel_path,
                    suggestion="save the manifest as UTF-8, or delete it and run `irminsul regen agents-md`",
                )
            ]
        out: list[Finding] = []

        start = text.find(GENERATED_START)
        end = text.find(GENERATED_END)
        if start == -1 or end == -1 or end < start:
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_MISSING_GENERATED_MARKERS,
                    severity=Severity.error,
                    message=(
                        f"agent manifest '{rel_path.as_posix()}' is missing the "
                        "generated-section markers"
                    ),
                    path=rel_path,
                    suggestion=suggestion,
                )
            )
        else:
            actual = text[start + len(GENERATED_START) : end].strip()
            expected = render_generated_section(graph).strip()
            if actual != expected:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_GENERATED_SECTION_DRIFT,
                        severity=Severity.error,
                        message=(
                            f"agent manifest '{rel_path.as_posix()}' generated section "
                            "has drifted from the doc graph"
                        ),
                        path=rel_path,
                        suggestion=suggestion,
                    )
                )

        for heading in self._REQUIRED_HEADINGS:
            if not re.search(rf"^#{{1,6}}\s+{re.escape(heading)}\s*$", text, re.MULTILINE):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_REQUIRED_HEADING,
                        severity=Severity.error,
                        message=(
                            f"agent manifest '{rel_path.as_posix()}' is missing the "
                            f"required '{heading}' heading"
                        ),
                        path=rel_path,
                        suggestion=f"Add a '## {heading}' section to the manifest",
                    )
                )

        return out


_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_LINK_DEST_RE = re.compile(r"\]\([^)\n]*\)")
_AUTOLINK_RE = re.compile(r"<[^>\s]+>")


def _mask_code_and_link_targets(line: str) -> str:
    # Inside backticks a term names a thing and inside a link target it is part of a
    # filename; neither is prose an author could reword to disambiguate.
    masked = line
    for pattern in (_INLINE_CODE_RE, _LINK_DEST_RE, _AUTOLINK_RE):
        masked = pattern.sub(lambda match: " " * len(match.group(0)), masked)
    return masked


def _line_has_term(line: str, term: str) -> bool:
    masked = _mask_code_and_link_targets(line)
    return re.search(rf"\b{re.escape(term)}\b", masked, re.IGNORECASE) is not None


def _term_is_explicit(line: str, rule: TerminologyRule) -> bool:
    lowered = line.lower()
    return any(phrase.lower() in lowered for phrase in rule.explicit_phrases)
