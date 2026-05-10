"""Deterministic doc-reality audits from RFC 0009."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.config import TerminologyRule
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import ClaimStateEnum, RfcStateEnum, StatusEnum
from irminsul.git.mtime import last_commit_time_any_repo
from irminsul.regen.doc_surfaces import surface_by_filename

_LOCAL_MD_RE = re.compile(r"(?<![\w.-])((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.md)(?![\w.-])")
_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\n]*\](?:\([^\)\n]*\)|\[[^\]\n]*\])")
_LINK_DEFINITION_RE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s+\S+")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
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


def _is_generated(node: DocNode, graph: DocGraph) -> bool:
    if graph.config is None:
        return False
    path = node.path.as_posix()
    return any(fnmatch.fnmatch(path, pattern) for pattern in graph.config.tiers.generated)


def _stable_audit_nodes(graph: DocGraph) -> list[DocNode]:
    return [
        node
        for node in graph.nodes.values()
        if node.frontmatter.status == StatusEnum.stable and not _is_generated(node, graph)
    ]


def _is_rfc_doc(node: DocNode) -> bool:
    return "/rfcs/" in node.path.as_posix()


def _is_protected_claim_node(node: DocNode, graph: DocGraph) -> bool:
    if graph.config is None:
        return False
    docs_root = _docs_root(graph)
    path = node.path.as_posix()
    return path.startswith(f"{docs_root}/00-foundation/") or path.startswith(
        f"{docs_root}/10-architecture/"
    )


def _line_link_spans(line: str) -> list[range]:
    if _LINK_DEFINITION_RE.match(line):
        return [range(0, len(line))]
    return [range(match.start(), match.end()) for match in _MARKDOWN_LINK_RE.finditer(line)]


def _inside_any(pos: int, spans: list[range]) -> bool:
    return any(pos in span for span in spans)


def _docs_root(graph: DocGraph) -> str:
    assert graph.config is not None
    return graph.config.paths.docs_root.strip("/\\")


def _claim_refs(text: str) -> set[str]:
    return {match.group(1) for match in _CLAIM_REF_RE.finditer(text)}


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
    in_fence = False

    def flush() -> None:
        nonlocal current, start_line
        if current and start_line is not None:
            paragraphs.append(_BodyParagraph(start_line=start_line, text="\n".join(current)))
        current = []
        start_line = None

    for lineno, line in enumerate(body.splitlines(), start=1):
        if _FENCE_RE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
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
    sections: list[_BodySection] = []
    current_heading: str | None = None
    current_level: int | None = None
    current_start: int | None = None
    current_lines: list[str] = []
    in_fence = False

    def flush() -> None:
        nonlocal current_heading, current_level, current_start, current_lines
        if current_heading is not None and current_start is not None:
            sections.append(
                _BodySection(
                    start_line=current_start,
                    heading=current_heading,
                    text="\n".join(current_lines),
                )
            )
        current_heading = None
        current_level = None
        current_start = None
        current_lines = []

    for lineno, line in enumerate(body.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            if current_heading is not None:
                current_lines.append(line)
            continue
        if not in_fence:
            match = _HEADING_RE.match(line)
            if match:
                level = len(match.group(1))
                if current_level is None or level <= current_level:
                    flush()
                    current_heading = match.group(2).strip()
                    current_level = level
                    current_start = lineno
                    continue
        if current_heading is not None:
            current_lines.append(line)
    flush()
    return sections


def _normalize_heading(heading: str) -> str:
    normalized = re.sub(r"\s+", " ", heading).strip().lower()
    if normalized.startswith("the "):
        normalized = normalized[4:]
    return normalized


class ProseFileReferenceCheck:
    name: ClassVar[str] = "prose-file-reference"
    default_severity: ClassVar[Severity] = Severity.error

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []

        for node in _stable_audit_nodes(graph):
            if _is_rfc_doc(node):
                continue

            in_fence = False
            in_ignore_block = False
            ignore_block_start: int | None = None
            for lineno, line in enumerate(node.body.splitlines(), start=1):
                if _FENCE_RE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                if _IGNORE_START_RE.search(line):
                    in_ignore_block = True
                    ignore_block_start = lineno
                    if _IGNORE_END_RE.search(line):
                        in_ignore_block = False
                        ignore_block_start = None
                    continue
                if _IGNORE_END_RE.search(line):
                    if not in_ignore_block:
                        out.append(
                            Finding(
                                check=self.name,
                                severity=self.default_severity,
                                message="ignore-end without matching ignore-start",
                                path=node.path,
                                doc_id=node.id,
                                line=lineno,
                                suggestion=(
                                    "Remove the unmatched ignore-end marker or add a matching "
                                    "ignore-start marker"
                                ),
                            )
                        )
                    in_ignore_block = False
                    ignore_block_start = None
                    continue
                if in_ignore_block or _IGNORE_RE.search(line):
                    continue

                link_spans = _line_link_spans(line)
                for match in _LOCAL_MD_RE.finditer(line):
                    if _inside_any(match.start(), link_spans):
                        continue
                    target = match.group(1)
                    out.append(
                        Finding(
                            check=self.name,
                            severity=self.default_severity,
                            message=(f"local markdown reference '{target}' is not a Markdown link"),
                            path=node.path,
                            doc_id=node.id,
                            line=lineno,
                            suggestion=(
                                "Convert it to a Markdown link or add "
                                "`<!-- irminsul:ignore prose-file-reference "
                                'reason="..." -->` on the line'
                            ),
                        )
                    )
                    break
            if in_ignore_block and ignore_block_start is not None:
                out.append(
                    Finding(
                        check=self.name,
                        severity=self.default_severity,
                        message="ignore-start without matching ignore-end",
                        path=node.path,
                        doc_id=node.id,
                        line=ignore_block_start,
                        suggestion="Add `<!-- irminsul:ignore-end prose-file-reference -->`",
                    )
                )

        return out


class ClaimProvenanceCheck:
    name: ClassVar[str] = "claim-provenance"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        out: list[Finding] = []
        for node in _stable_audit_nodes(graph):
            if not _is_protected_claim_node(node, graph):
                continue

            claim_ids = {claim.id for claim in node.frontmatter.claims}
            out.extend(self._validate_evidence(graph, node))
            out.extend(self._validate_body_claim_refs(node, claim_ids))
            out.extend(self._scan_risky_prose(node, claim_ids))
            out.extend(self._scan_structured_sections(node, claim_ids))
            out.extend(self._scan_evidence_drift(graph, node))
            out.extend(self._scan_planned_claim_lifecycle(graph, node))

        return out

    def _validate_evidence(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        assert graph.config is not None
        assert graph.repo_root is not None

        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            evidence_paths = [Path(evidence) for evidence in claim.evidence]
            for evidence, rel_path in zip(claim.evidence, evidence_paths, strict=True):
                if Path(evidence).is_absolute():
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=(
                                f"claim '{claim.id}' evidence must be repo-relative: '{evidence}'"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion="Use a repo-relative evidence path",
                        )
                    )
                    continue
                if not (graph.repo_root / rel_path).exists():
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.error,
                            message=f"claim '{claim.id}' evidence path does not exist: '{evidence}'",
                            path=node.path,
                            doc_id=node.id,
                            suggestion="Point the claim at existing source, config, CI, or doc evidence",
                        )
                    )

            if not self._has_state_appropriate_evidence(graph, claim.state, evidence_paths):
                out.append(
                    Finding(
                        check=self.name,
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
        evidence_paths: list[Path],
    ) -> bool:
        if state == ClaimStateEnum.planned:
            return any(self._is_rfc_evidence(graph, path) for path in evidence_paths)
        if state == ClaimStateEnum.implemented:
            return any(self._is_implementation_evidence(graph, path) for path in evidence_paths)
        if state == ClaimStateEnum.available:
            return any(
                self._is_implementation_evidence(graph, path) for path in evidence_paths
            ) and any(self._is_enablement_doc_evidence(graph, path) for path in evidence_paths)
        if state == ClaimStateEnum.enabled:
            return any(self._is_enabled_evidence(path) for path in evidence_paths)
        if state == ClaimStateEnum.external:
            return any(self._is_external_process_evidence(graph, path) for path in evidence_paths)
        return False

    def _state_suggestion(self, state: ClaimStateEnum) -> str:
        suggestions = {
            ClaimStateEnum.planned: "Add an RFC evidence path under docs/80-evolution/rfcs/",
            ClaimStateEnum.implemented: "Add source or component-doc implementation evidence",
            ClaimStateEnum.available: "Add implementation evidence plus user-facing enablement docs",
            ClaimStateEnum.enabled: "Add irminsul.toml, action.yml, or .github/workflows evidence",
            ClaimStateEnum.external: "Add process, operation, external-tool, or config documentation",
        }
        return suggestions[state]

    def _validate_body_claim_refs(self, node: DocNode, claim_ids: set[str]) -> list[Finding]:
        out: list[Finding] = []
        in_fence = False
        for lineno, line in enumerate(node.body.splitlines(), start=1):
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for match in _CLAIM_REF_RE.finditer(line):
                claim_id = match.group(1)
                if claim_id not in claim_ids:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.warning,
                            message=f"unknown structured claim reference: 'claim:{claim_id}'",
                            path=node.path,
                            doc_id=node.id,
                            line=lineno,
                            suggestion="Add a matching frontmatter claim or remove the marker",
                        )
                    )
        return out

    def _scan_risky_prose(self, node: DocNode, claim_ids: set[str]) -> list[Finding]:
        out: list[Finding] = []
        for paragraph in _body_paragraphs(node.body):
            if _RISKY_CLAIM_RE.search(paragraph.text) is None:
                continue
            if any(claim_id in claim_ids for claim_id in _claim_refs(paragraph.text)):
                continue
            out.append(
                Finding(
                    check=self.name,
                    severity=Severity.warning,
                    message="high-risk enforcement or automation prose lacks a structured claim reference",
                    path=node.path,
                    doc_id=node.id,
                    line=paragraph.start_line,
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
                    severity=Severity.warning,
                    message=f"section '{section.heading}' needs a structured claim reference",
                    path=node.path,
                    doc_id=node.id,
                    line=section.start_line,
                    suggestion="Add at least one relevant `claim:<id>` marker in this section",
                )
            )
        return out

    def _scan_evidence_drift(self, graph: DocGraph, node: DocNode) -> list[Finding]:
        assert graph.repo_root is not None

        doc_time = last_commit_time_any_repo(graph.repo_root / node.path, graph.repo_root)
        if doc_time is None or doc_time.when is None:
            return []

        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            latest_path: str | None = None
            latest_time = None
            for evidence in claim.evidence:
                evidence_abs = graph.repo_root / evidence
                if not evidence_abs.exists():
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

        resolved_states = {
            RfcStateEnum.accepted,
            RfcStateEnum.rejected,
            RfcStateEnum.withdrawn,
        }
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
                        severity=Severity.warning,
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
        docs_root = _docs_root(graph)
        return (
            path.as_posix().startswith(f"{docs_root}/80-evolution/rfcs/") and path.suffix == ".md"
        )

    def _is_source_evidence(self, graph: DocGraph, path: Path) -> bool:
        assert graph.config is not None
        path_posix = path.as_posix()
        return any(
            path_posix == root.strip("/\\") or path_posix.startswith(f"{root.strip('/\\')}/")
            for root in graph.config.paths.source_roots
        )

    def _is_component_doc_evidence(self, graph: DocGraph, path: Path) -> bool:
        docs_root = _docs_root(graph)
        return path.as_posix().startswith(f"{docs_root}/20-components/")

    def _is_implementation_evidence(self, graph: DocGraph, path: Path) -> bool:
        return self._is_source_evidence(graph, path) or self._is_component_doc_evidence(graph, path)

    def _is_enablement_doc_evidence(self, graph: DocGraph, path: Path) -> bool:
        path_posix = path.as_posix()
        docs_root = _docs_root(graph)
        return (
            path_posix.startswith(f"{docs_root}/")
            and not path_posix.startswith(f"{docs_root}/80-evolution/rfcs/")
        ) or self._is_enabled_evidence(path)

    def _is_enabled_evidence(self, path: Path) -> bool:
        path_posix = path.as_posix()
        return (
            path_posix == "irminsul.toml"
            or path_posix == "action.yml"
            or (path_posix.startswith(".github/workflows/") and path.suffix in {".yml", ".yaml"})
        )

    def _is_external_process_evidence(self, graph: DocGraph, path: Path) -> bool:
        path_posix = path.as_posix()
        docs_root = _docs_root(graph)
        return (
            path_posix.startswith(f"{docs_root}/")
            or path_posix == "irminsul.toml"
            or path_posix == "action.yml"
            or path_posix == ".pre-commit-config.yaml"
            or path_posix.startswith(".github/")
        ) and not self._is_source_evidence(graph, path)


class _GeneratedSurfaceDriftCheck:
    name: ClassVar[str]
    default_severity: ClassVar[Severity] = Severity.warning
    surface_filename: ClassVar[str]
    relevant_doc_ids: ClassVar[set[str]]

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.repo_root is None or graph.config is None:
            return []

        rel_path = Path(graph.config.paths.docs_root) / "40-reference" / self.surface_filename
        if not self._is_applicable(graph, rel_path):
            return []

        expected = surface_by_filename(self.surface_filename)
        if expected is None:
            return []

        abs_path = graph.repo_root / rel_path
        if not abs_path.exists():
            return [
                Finding(
                    check=self.name,
                    severity=self.default_severity,
                    message=f"generated reference '{rel_path.as_posix()}' is missing",
                    path=rel_path,
                    suggestion="Run `irminsul regen --language=docs-surfaces`",
                )
            ]

        actual = abs_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if actual != expected.content:
            return [
                Finding(
                    check=self.name,
                    severity=self.default_severity,
                    message=f"generated reference '{rel_path.as_posix()}' is stale",
                    path=rel_path,
                    suggestion="Run `irminsul regen --language=docs-surfaces`",
                )
            ]
        return []

    def _is_applicable(self, graph: DocGraph, rel_path: Path) -> bool:
        if rel_path in graph.by_path:
            return True
        return any(doc_id in graph.nodes for doc_id in self.relevant_doc_ids)


class SchemaDocDriftCheck(_GeneratedSurfaceDriftCheck):
    name: ClassVar[str] = "schema-doc-drift"
    surface_filename: ClassVar[str] = "frontmatter-fields.md"
    relevant_doc_ids: ClassVar[set[str]] = {"frontmatter", "doc-atom"}


class CliDocDriftCheck(_GeneratedSurfaceDriftCheck):
    name: ClassVar[str] = "cli-doc-drift"
    surface_filename: ClassVar[str] = "cli-commands.md"
    relevant_doc_ids: ClassVar[set[str]] = {"cli"}


class CheckSurfaceDriftCheck(_GeneratedSurfaceDriftCheck):
    name: ClassVar[str] = "check-surface-drift"
    surface_filename: ClassVar[str] = "check-registries.md"
    relevant_doc_ids: ClassVar[set[str]] = {"checks"}


class TerminologyOverloadCheck:
    name: ClassVar[str] = "terminology-overload"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        out: list[Finding] = []
        rules = graph.config.checks.terminology_overload.rules
        for node in _stable_audit_nodes(graph):
            if _is_rfc_doc(node):
                continue
            in_fence = False
            for lineno, line in enumerate(node.body.splitlines(), start=1):
                if _FENCE_RE.match(line):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                for rule in rules:
                    if not _line_has_term(line, rule.term):
                        continue
                    if _term_is_explicit(line, rule):
                        continue
                    out.append(
                        Finding(
                            check=self.name,
                            severity=self.default_severity,
                            message=f"'{rule.term}' is ambiguous here",
                            path=node.path,
                            doc_id=node.id,
                            line=lineno,
                            suggestion=rule.suggestion,
                        )
                    )
        return out


def _line_has_term(line: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", line, re.IGNORECASE) is not None


def _term_is_explicit(line: str, rule: TerminologyRule) -> bool:
    lowered = line.lower()
    return any(phrase.lower() in lowered for phrase in rule.explicit_phrases)
