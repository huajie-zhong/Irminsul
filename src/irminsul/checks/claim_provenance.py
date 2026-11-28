"""ClaimProvenanceCheck — a declared claim cites evidence that exists, fits its state, and has not changed since."""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from irminsul.anchors import Resolution, file_pin, resolve_evidence
from irminsul.checks.base import (
    Answer,
    CheckFlag,
    Finding,
    FindingClass,
    Severity,
    certain_audit_nodes,
    closest,
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
from irminsul.parts import split_part

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
CODE_EVIDENCE_PART_MISSING = "claim-provenance/evidence-part-missing"
CODE_EVIDENCE_PART_UNSUPPORTED = "claim-provenance/evidence-part-unsupported"
CODE_EVIDENCE_STATE_MISMATCH = "claim-provenance/evidence-state-mismatch"
CODE_UNKNOWN_CLAIM_REF = "claim-provenance/unknown-claim-ref"
CODE_EVIDENCE_DRIFT = "claim-provenance/evidence-drift"

_UNRESOLVED = ("missing_symbol", "unsupported", "missing_file")
"""What a part that names nothing resolves as: a name its file's finder does not know, a
part of a file whose type has no finder, and a part of what is no file."""


@dataclass(frozen=True)
class _Entry:
    """One evidence entry of a claim, as it is written and where it leads."""

    path: Path
    """The entry's path as the claim writes it, without the part it may name."""
    file: Path | None
    """The file or directory that path resolves to, None when nothing is there."""
    part: str | None
    found: Resolution | None
    """The part's resolution in the file; None for a bare path and where the path leads
    nowhere."""

    @property
    def unresolved(self) -> bool:
        """Whether the entry names a part that is not there, which is reported on its own
        and judged for no drift."""
        return self.found is not None and self.found.status in _UNRESOLVED

    @property
    def pin(self) -> str | None:
        """The part's current pin, None for a bare path or a part with no hash."""
        if self.found is None or self.found.status != "ok":
            return None
        return f"sha256:{self.found.current}"


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
        CODE_EVIDENCE_PART_MISSING: (
            "A claim's evidence entry `path#part` names a part its file does not hold, "
            "usually because the part was renamed: a definition the file's reader does not "
            "find, a heading no slug matches or two share, a key that is not there, or a "
            "marker opened twice or never closed. Nothing searches the text for the name. "
            "Point the entry at the part's current name, which the message offers among the "
            "closest the file has."
        ),
        CODE_EVIDENCE_PART_UNSUPPORTED: (
            "A claim's evidence entry names a part of a file whose type has no finder: no "
            "language reader reads it, and it is not Markdown, TOML, YAML or JSON. Mark the "
            "lines the claim rests on with `irminsul:part <name>` and `irminsul:end <name>` "
            "in comments of the file, or cite the whole file by dropping `#<name>`."
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
            "--claim <id> --evidence <entry>` pins the evidence the finding names as re-read. "
            "An entry that names a part, `path#part`, is pinned by that part, so a change "
            "elsewhere in its file does not ask again."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_EVIDENCE_NOT_REPO_RELATIVE: FindingClass.certain,
        CODE_EVIDENCE_PATH_MISSING: FindingClass.certain,
        CODE_EVIDENCE_PART_MISSING: FindingClass.certain,
        CODE_EVIDENCE_PART_UNSUPPORTED: FindingClass.certain,
        CODE_EVIDENCE_STATE_MISMATCH: FindingClass.certain,
        CODE_UNKNOWN_CLAIM_REF: FindingClass.certain,
        CODE_EVIDENCE_DRIFT: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_EVIDENCE_DRIFT: Answer.pin(
            "re-read the claim against the evidence it names, then run `irminsul anchors "
            "--re-pin --doc <doc> --claim <id> --evidence <entry>`"
        ),
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

    def _resolve_evidence(self, graph: DocGraph, evidence: str) -> _Entry:
        """An entry split at its first `#`: the path is what exists, is of a state and has
        an owner, and the part is found in the file as an anchor's part is."""
        assert graph.config is not None
        assert graph.repo_root is not None
        path, part = split_part(evidence)
        file = resolve_display_path(graph.repo_root, graph.config.paths.source_roots, path)
        found = None if part is None or file is None else resolve_evidence(file, part, graph.source)
        return _Entry(Path(path), file, part, found)

    def _resolve_node_evidence(self, graph: DocGraph, node: DocNode) -> dict[str, _Entry]:
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
        self, graph: DocGraph, node: DocNode, resolved: dict[str, _Entry]
    ) -> list[Finding]:
        assert graph.config is not None
        assert graph.repo_root is not None

        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            entries = [resolved[evidence] for evidence in claim.evidence]
            evidence_refs = [(entry.path, entry.file) for entry in entries]
            for evidence, entry in zip(claim.evidence, entries, strict=True):
                rel_path, resolved_path = entry.path, entry.file
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
                    continue
                if entry.unresolved:
                    out.append(self._part_finding(node, claim.id, evidence, entry))

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

    def _part_finding(self, node: DocNode, claim_id: str, evidence: str, entry: _Entry) -> Finding:
        """The certain finding for an entry whose part is not in its file. A part of a file
        with a finder is missing, with the closest names that finder knows; a part of a
        file with none, or of a directory, is unsupported, and the answer is a marker."""
        assert entry.found is not None
        part, found = entry.part or "", entry.found
        path = entry.path.as_posix()
        if found.status == "missing_symbol":
            reason = f": {found.why}" if found.why else ""
            return Finding(
                check=self.name,
                code=CODE_EVIDENCE_PART_MISSING,
                severity=Severity.error,
                message=(
                    f"claim '{claim_id}' evidence part '{part}' is not in '{path}'"
                    f"{reason}{closest(part, found.known)}"
                ),
                path=node.path,
                doc_id=node.id,
                suggestion=(
                    "point the entry at the part's current name, or at the whole file by "
                    f"dropping `#{part}`"
                ),
            )
        what = (
            "it is not a file"
            if found.status == "missing_file"
            else (
                f"no finder reads this type of file and no `irminsul:part {part}` marker is in it"
            )
        )
        return Finding(
            check=self.name,
            code=CODE_EVIDENCE_PART_UNSUPPORTED,
            severity=Severity.error,
            message=(
                f"claim '{claim_id}' evidence part '{part}' cannot be found in '{path}': "
                f"{what}{closest(part, found.known)}"
            ),
            path=node.path,
            doc_id=node.id,
            suggestion=(
                f"mark the lines with `irminsul:part {part}` and `irminsul:end {part}` in "
                f"comments of the file, or cite the whole file by dropping `#{part}`"
            ),
        )

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
        resolved: dict[str, _Entry],
        pins: dict[Path, str | None],
    ) -> list[Finding]:
        """A claim whose evidence was committed after the doc, unless the claim pins that
        entry and what it names still has the pinned hash: the part, for an entry that
        names one, and the whole file otherwise.

        A pin only ever removes drift. One that no longer matches, because the evidence
        changed, the pin was written in an older format, or the doc was updated beside the
        evidence without a re-pin, falls back to the commit-time comparison of the entry's
        file, so pinning never reports more than not pinning would, and a part with no pin
        is asked about as its whole file is. An entry whose part is not in its file is
        reported for that and judged for no drift. `pins` memoizes each whole file's hash
        for the run: several claims cite the same file.
        """
        assert graph.repo_root is not None

        doc_read = False
        doc_when: _dt.datetime | None = None
        out: list[Finding] = []
        for claim in node.frontmatter.claims:
            changed: list[tuple[str, _dt.datetime, bool]] = []
            for evidence in claim.evidence:
                entry = resolved[evidence]
                evidence_abs = entry.file
                if evidence_abs is None or entry.unresolved:
                    continue
                pin = claim.pinned.get(evidence)
                if pin is not None:
                    if entry.part is None and evidence_abs not in pins:
                        pins[evidence_abs] = file_pin(evidence_abs, graph.source)
                    current = pins[evidence_abs] if entry.part is None else entry.pin
                    if current == pin:
                        continue
                evidence_time = last_commit_time_any_repo(graph.git, evidence_abs, graph.repo_root)
                if evidence_time is None or evidence_time.when is None:
                    continue
                changed.append((evidence, evidence_time.when, pin is not None))
            if not changed:
                continue
            if not doc_read:
                doc_read = True
                doc_time = last_commit_time_any_repo(
                    graph.git, graph.repo_root / node.path, graph.repo_root
                )
                doc_when = doc_time.when if doc_time is not None else None
            if doc_when is None:
                continue
            drifted = [(path, pinned) for path, when, pinned in changed if when > doc_when]
            if drifted:
                out.append(self._drift_finding(node, claim.id, drifted))
        return out

    def _drift_finding(
        self, node: DocNode, claim_id: str, drifted: list[tuple[str, bool]]
    ) -> Finding:
        """One finding for a claim, naming every evidence entry that drifted as the claim
        spells it, and a re-pin narrowed to those entries: a pin of the claim's other
        evidence that no longer matches is not what the reader was asked to re-read."""
        since = ""
        if all(pinned for _, pinned in drifted):
            since = (
                " and since it was pinned" if len(drifted) == 1 else " and since they were pinned"
            )
        named = ", ".join(f"'{path}'" for path, _ in drifted)
        evidence = "".join(f" --evidence {path}" for path, _ in drifted)
        return Finding(
            check=self.name,
            code=CODE_EVIDENCE_DRIFT,
            severity=Severity.warning,
            message=f"claim '{claim_id}' cites evidence changed after the doc{since}: {named}",
            path=node.path,
            doc_id=node.id,
            suggestion=(
                "Review the claim against the evidence named and update the doc if it changed "
                "the claim's truth; if it still holds, record that with "
                f"`irminsul anchors --re-pin --doc {node.path.as_posix()} "
                f"--claim {claim_id}{evidence}`"
            ),
        )

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
