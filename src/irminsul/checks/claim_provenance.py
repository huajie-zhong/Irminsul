"""ClaimProvenanceCheck — a declared claim cites evidence that exists, fits its state, and has not changed since."""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import ClassVar

from irminsul.anchors import file_pin
from irminsul.checks.base import (
    CheckFlag,
    Finding,
    FindingClass,
    Severity,
    certain_audit_nodes,
)
from irminsul.checks.globs import (
    is_external_source_location,
    is_source_path,
    resolve_display_path,
    source_root_prefixes,
)
from irminsul.config import in_layer
from irminsul.docgraph import DocGraph, DocNode
from irminsul.fences import FenceTracker
from irminsul.frontmatter import ClaimStateEnum, StatusEnum
from irminsul.git.mtime import last_commit_time_any_repo

_CLAIM_REF_RE = re.compile(r"claim:([A-Za-z0-9_.-]+)")
_EVIDENCE_SPELLING_SUGGESTION = (
    "Spell evidence the way `describes:` does: repo-relative inside the docs repo, "
    "source-root-relative for files under a source root outside it"
)


def _is_protected_claim_node(node: DocNode, graph: DocGraph) -> bool:
    if graph.config is None:
        return False
    return in_layer(graph.config, node.path, "foundation") or in_layer(
        graph.config, node.path, "architecture"
    )


def _docs_root(graph: DocGraph) -> str:
    assert graph.config is not None
    return graph.config.paths.docs_root.strip("/\\")


CODE_EVIDENCE_NOT_REPO_RELATIVE = "claim-provenance/evidence-not-repo-relative"
CODE_EVIDENCE_PATH_MISSING = "claim-provenance/evidence-path-missing"
CODE_EVIDENCE_STATE_MISMATCH = "claim-provenance/evidence-state-mismatch"
CODE_UNKNOWN_CLAIM_REF = "claim-provenance/unknown-claim-ref"
CODE_EVIDENCE_DRIFT = "claim-provenance/evidence-drift"


class ClaimProvenanceCheck:
    """A declared claim cites evidence that exists, fits its state, and has not changed since."""

    name: ClassVar[str] = "claim-provenance"
    default_severity: ClassVar[Severity] = Severity.warning
    flags: ClassVar[frozenset[CheckFlag]] = frozenset({CheckFlag.reads_history})
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
        CODE_EVIDENCE_DRIFT: (
            "A claim's evidence was committed after the doc was and, where the claim pins "
            "it, no longer has the pinned hash. Review whether the claim is still true and "
            "update the doc if not; if it is, `irminsul anchors --re-pin --doc <doc> "
            "--claim <id>` pins that claim's evidence as re-read."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_EVIDENCE_NOT_REPO_RELATIVE: FindingClass.certain,
        CODE_EVIDENCE_PATH_MISSING: FindingClass.certain,
        CODE_EVIDENCE_STATE_MISMATCH: FindingClass.certain,
        CODE_UNKNOWN_CLAIM_REF: FindingClass.certain,
        CODE_EVIDENCE_DRIFT: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        out: list[Finding] = []
        pins: dict[Path, str | None] = {}
        for node in certain_audit_nodes(graph):
            claim_ids = {claim.id for claim in node.frontmatter.claims}
            resolved = self._resolve_node_evidence(graph, node)
            out.extend(self._validate_evidence(graph, node, resolved))
            out.extend(self._validate_body_claim_refs(node, claim_ids))
            if not _is_protected_claim_node(node, graph):
                continue
            # Drift is a hint about finished prose, which a draft is not yet. A planned claim
            # citing a resolved RFC is `rfc-follow-through`'s `stale-claim`.
            if node.frontmatter.status == StatusEnum.stable:
                out.extend(self._scan_evidence_drift(graph, node, resolved, pins))

        return out

    def _resolve_evidence(self, graph: DocGraph, evidence: str) -> Path | None:
        assert graph.config is not None
        assert graph.repo_root is not None
        return resolve_display_path(graph.repo_root, graph.config.paths.source_roots, evidence)

    def _resolve_node_evidence(self, graph: DocGraph, node: DocNode) -> dict[str, Path | None]:
        """Every evidence spelling of the node, resolved once.

        `_validate_evidence`, `_scan_evidence_drift`, and the source
        classifiers all need the same answer; resolving here keeps it to one
        disk probe per spelling instead of one per consumer.
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

    def _scan_evidence_drift(
        self,
        graph: DocGraph,
        node: DocNode,
        resolved: dict[str, Path | None],
        pins: dict[Path, str | None],
    ) -> list[Finding]:
        """A claim whose evidence was committed after the doc, unless the claim pins that
        evidence and the file still has the pinned hash.

        A pin only ever removes drift. One that no longer matches, because the evidence
        changed, the pin was written in an older format, or the doc was updated beside the
        evidence without a re-pin, falls back to the commit-time comparison, so pinning
        never reports more than not pinning would. `pins` memoizes
        each file's hash for the run: several claims cite the same file.
        """
        assert graph.repo_root is not None

        doc_read = False
        doc_when: _dt.datetime | None = None
        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            latest_path: str | None = None
            latest_time: _dt.datetime | None = None
            latest_pinned = False
            for evidence in claim.evidence:
                evidence_abs = resolved.get(evidence)
                if evidence_abs is None:
                    continue
                pin = claim.pinned.get(evidence)
                if pin is not None:
                    if evidence_abs not in pins:
                        pins[evidence_abs] = file_pin(evidence_abs, graph.source)
                    if pins[evidence_abs] == pin:
                        continue
                evidence_time = last_commit_time_any_repo(graph.git, evidence_abs, graph.repo_root)
                if evidence_time is None or evidence_time.when is None:
                    continue
                if latest_time is None or evidence_time.when > latest_time:
                    latest_time = evidence_time.when
                    latest_path = evidence
                    latest_pinned = pin is not None
            if latest_time is None:
                continue
            if not doc_read:
                doc_read = True
                doc_time = last_commit_time_any_repo(
                    graph.git, graph.repo_root / node.path, graph.repo_root
                )
                doc_when = doc_time.when if doc_time is not None else None
            if doc_when is None or latest_time <= doc_when:
                continue
            since = " and since it was pinned" if latest_pinned else ""
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_EVIDENCE_DRIFT,
                    severity=Severity.warning,
                    message=(
                        f"claim '{claim.id}' cites evidence changed after the doc{since}: "
                        f"'{latest_path}'"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=(
                        "Review the claim and update the doc if the evidence changed its "
                        "truth; if it still holds, record that with "
                        f"`irminsul anchors --re-pin --doc {node.path.as_posix()} "
                        f"--claim {claim.id}`"
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
        "process evidence and not source", so an unconditional yes would make every
        external claim unsatisfiable, and `implemented`/`available` would stop
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
