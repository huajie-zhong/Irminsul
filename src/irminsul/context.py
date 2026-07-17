"""Runtime context lookup for agents and contributors."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from pathspec import GitIgnoreSpec

from irminsul.checks import HARD_REGISTRY, SOFT_REGISTRY, Check, Finding, sort_findings
from irminsul.checks.globs import is_source_path, source_root_prefixes
from irminsul.checks.uniqueness import specificity
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode, build_graph
from irminsul.frontmatter import RfcStateEnum, canonical_rfc_state
from irminsul.git.changes import GitChangesError, working_tree_changed_paths

ContextMode = Literal["path", "topic", "changed"]
ContextProfile = Literal["hard", "configured", "all-available"]
WorkflowStage = Literal["before-edit", "after-edit"]


class ContextError(Exception):
    """User-facing context command error."""

    def __init__(self, message: str, *, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DocRef:
    id: str
    title: str
    path: str
    status: str
    audience: str
    tier: int


@dataclass(frozen=True)
class FindingSummary:
    check: str
    severity: str
    message: str
    path: str | None
    doc_id: str | None
    line: int | None
    suggestion: str | None


@dataclass(frozen=True)
class RequirementRef:
    id: str | None
    title: str


@dataclass(frozen=True)
class ActiveChange:
    id: str
    title: str
    path: str
    state: str
    requirements: list[RequirementRef]


@dataclass(frozen=True)
class WorkflowValidation:
    hard_checks_passed: bool
    errors: int
    warnings: int


@dataclass(frozen=True)
class NextAction:
    command: str
    reason: str


@dataclass(frozen=True)
class ContextResult:
    input: list[str]
    owner: DocRef
    source_claims: list[str]
    entrypoint: str | None
    tests: list[str]
    depends_on: list[DocRef]
    depends_on_missing: list[str]
    depended_on_by: list[DocRef]
    findings: list[FindingSummary]
    hints: list[str]
    active_changes: list[ActiveChange] = field(default_factory=list)
    doc_co_changed: bool = True


@dataclass(frozen=True)
class UnmatchedPath:
    path: str
    reason: str
    candidates: list[DocRef]


@dataclass(frozen=True)
class ContextReport:
    version: int
    mode: ContextMode
    results: list[ContextResult]
    unmatched: list[UnmatchedPath]
    workflow: WorkflowStage | None = None
    validation: WorkflowValidation | None = None
    next_actions: list[NextAction] = field(default_factory=list)


@dataclass(frozen=True)
class _Ownership:
    node: DocNode | None
    pattern: str | None
    candidates: tuple[DocNode, ...]
    reason: str | None


@dataclass(frozen=True)
class _ClaimSpec:
    node: DocNode
    pattern: str
    score: tuple[int, int, int]
    spec: GitIgnoreSpec


@dataclass(frozen=True)
class _PendingResult:
    node: DocNode
    inputs: tuple[str, ...]
    source_claims: tuple[str, ...]
    doc_co_changed: bool = True


@dataclass
class _ChangedGroup:
    node: DocNode
    inputs: set[str]
    source_claims: set[str]


Registry = Mapping[str, type[Check]]


def build_context_report(
    repo_root: Path,
    config: IrminsulConfig,
    *,
    target_path: Path | None = None,
    target_paths: Iterable[Path] | None = None,
    topic: str | None = None,
    changed: bool = False,
    profile: ContextProfile = "configured",
    workflow: WorkflowStage | None = None,
) -> ContextReport:
    """Build task-specific navigation context from the current doc graph."""
    paths = tuple(target_paths) if target_paths is not None else None
    if target_path is not None and paths is not None:
        raise ContextError("target_path and target_paths cannot be combined", code=2)

    has_path_input = target_path is not None or paths is not None
    selected_modes = sum(
        [
            has_path_input,
            topic is not None,
            changed,
        ]
    )
    if selected_modes != 1:
        raise ContextError(
            "choose exactly one input mode: <path>, --topic <query>, or --changed",
            code=2,
        )
    if workflow == "before-edit" and not has_path_input:
        raise ContextError("before-edit requires one or more paths", code=2)
    if workflow == "after-edit" and not changed:
        raise ContextError("after-edit requires changed-path mode", code=2)
    if workflow not in (None, "before-edit", "after-edit"):
        raise ContextError(f"unknown context workflow: {workflow}", code=2)

    graph = build_graph(repo_root, config)

    if has_path_input:
        requested_paths = paths if paths is not None else (target_path,)
        pending, unmatched = _pending_for_paths(
            repo_root,
            graph,
            tuple(path for path in requested_paths if path is not None),
        )
        mode: ContextMode = "path"
    elif topic is not None:
        pending = _pending_for_topic(graph, topic)
        unmatched = []
        mode = "topic"
    else:
        pending, unmatched = _pending_for_changed(repo_root, graph)
        mode = "changed"

    findings = (
        _run_deterministic_checks(config, graph, profile) if pending or workflow is not None else []
    )
    include_workflow = workflow is not None
    results = [
        _build_result(
            graph,
            item,
            findings,
            include_active_changes=include_workflow,
        )
        for item in pending
    ]
    validation = _workflow_validation(config, findings, profile) if include_workflow else None
    next_actions = (
        _workflow_next_actions(
            workflow,
            results,
            unmatched,
            validation,
            has_unowned_source=_has_unowned_source(repo_root, config, unmatched),
        )
        if workflow is not None
        else []
    )
    return ContextReport(
        version=1,
        mode=mode,
        results=results,
        unmatched=unmatched,
        workflow=workflow,
        validation=validation,
        next_actions=next_actions,
    )


def context_report_should_fail(report: ContextReport) -> bool:
    """Whether the CLI should return non-zero after printing a report."""
    if (
        report.workflow == "after-edit"
        and report.validation is not None
        and not report.validation.hard_checks_passed
    ):
        return True
    return report.mode == "path" and not report.results


def context_report_to_json(report: ContextReport) -> str:
    return json.dumps(_report_to_dict(report), indent=2)


def format_context_plain(report: ContextReport) -> str:
    lines: list[str] = []
    if not report.results and not report.unmatched and report.workflow is None:
        return "(none)"

    if report.workflow is not None:
        lines.append(f"Workflow: {report.workflow}")

    for result in report.results:
        if lines:
            lines.append("")
        lines.extend(_format_result(result, include_workflow=report.workflow is not None))

    if report.unmatched:
        if lines:
            lines.append("")
        lines.append("Unmatched:")
        for item in report.unmatched:
            suffix = ""
            if item.candidates:
                ids = ", ".join(doc.id for doc in item.candidates)
                suffix = f" (candidates: {ids})"
            lines.append(f"  {item.path}: {item.reason}{suffix}")
        if report.workflow is None:
            lines.append("  hint: irminsul list undocumented --all")

    if report.workflow is not None:
        if lines:
            lines.append("")
        validation = report.validation
        if validation is not None:
            state = "passed" if validation.hard_checks_passed else "failed"
            lines.append(
                "Hard validation: "
                f"{state} ({validation.errors} errors, {validation.warnings} warnings)"
            )
        lines.append("Next actions:")
        if report.next_actions:
            for action in report.next_actions:
                lines.append(f"  {action.command}")
                lines.append(f"    reason: {action.reason}")
        else:
            lines.append("  (none)")

    return "\n".join(lines)


def _pending_for_paths(
    repo_root: Path,
    graph: DocGraph,
    target_paths: tuple[Path, ...],
) -> tuple[list[_PendingResult], list[UnmatchedPath]]:
    if not target_paths:
        raise ContextError("path input cannot be empty", code=2)

    groups: dict[str, _ChangedGroup] = {}
    unmatched: list[UnmatchedPath] = []
    for target_path in target_paths:
        path_pending, path_unmatched = _pending_for_path(repo_root, graph, target_path)
        unmatched.extend(path_unmatched)
        for item in path_pending:
            group = groups.setdefault(
                item.node.id,
                _ChangedGroup(node=item.node, inputs=set(), source_claims=set()),
            )
            group.inputs.update(item.inputs)
            group.source_claims.update(item.source_claims)

    pending = [
        _PendingResult(
            node=group.node,
            inputs=tuple(sorted(group.inputs)),
            source_claims=tuple(sorted(group.source_claims)),
        )
        for group in sorted(groups.values(), key=lambda item: item.node.path.as_posix())
    ]
    unmatched.sort(key=lambda item: item.path)
    return pending, unmatched


def _pending_for_path(
    repo_root: Path,
    graph: DocGraph,
    target_path: Path,
) -> tuple[list[_PendingResult], list[UnmatchedPath]]:
    rel = _existing_repo_relative(repo_root, target_path)
    display = rel.as_posix()

    node = graph.by_path.get(rel)
    if node is not None:
        return [
            _PendingResult(
                node=node,
                inputs=(display,),
                source_claims=tuple(node.frontmatter.describes),
            )
        ], []

    ownership = _ownership_for_source_path(display, _claim_specs(graph))
    if ownership.node is not None:
        return [
            _PendingResult(
                node=ownership.node,
                inputs=(display,),
                source_claims=(ownership.pattern,) if ownership.pattern else (),
            )
        ], []

    return [], [
        UnmatchedPath(
            path=display,
            reason=ownership.reason or "no owning doc found",
            candidates=[_doc_ref(node) for node in ownership.candidates],
        )
    ]


def _pending_for_topic(graph: DocGraph, topic: str) -> list[_PendingResult]:
    query = topic.strip()
    if not query:
        raise ContextError("topic query cannot be empty", code=2)

    query_lower = query.lower()
    matches = [node for node in graph.nodes.values() if _node_matches_topic(node, query_lower)]
    if not matches:
        return []

    matches = sorted(
        matches,
        key=lambda node: (
            0 if node.id.lower() == query_lower else 1,
            node.path.as_posix(),
            node.frontmatter.title.lower(),
            node.id,
        ),
    )
    return [
        _PendingResult(
            node=node,
            inputs=(query,),
            source_claims=tuple(node.frontmatter.describes),
        )
        for node in matches
    ]


def _pending_for_changed(
    repo_root: Path,
    graph: DocGraph,
) -> tuple[list[_PendingResult], list[UnmatchedPath]]:
    groups: dict[str, _ChangedGroup] = {}
    unmatched: list[UnmatchedPath] = []
    claim_specs = _claim_specs(graph)
    test_owners = _declared_test_owners(graph)

    changed_paths = _git_changed_paths(repo_root)
    changed_set = set(changed_paths)

    for changed_path in changed_paths:
        rel = Path(PurePosixPath(changed_path))
        node = graph.by_path.get(rel)
        if node is not None:
            group = groups.setdefault(
                node.id,
                _ChangedGroup(node=node, inputs=set(), source_claims=set()),
            )
            group.inputs.add(changed_path)
            group.source_claims.update(node.frontmatter.describes)
            continue

        declared_owners = test_owners.get(changed_path, ())
        if declared_owners:
            for declared_owner in declared_owners:
                group = groups.setdefault(
                    declared_owner.id,
                    _ChangedGroup(node=declared_owner, inputs=set(), source_claims=set()),
                )
                group.inputs.add(changed_path)
            continue

        ownership = _ownership_for_source_path(changed_path, claim_specs)
        if ownership.node is not None:
            group = groups.setdefault(
                ownership.node.id,
                _ChangedGroup(node=ownership.node, inputs=set(), source_claims=set()),
            )
            group.inputs.add(changed_path)
            if ownership.pattern:
                group.source_claims.add(ownership.pattern)
            continue

        unmatched.append(
            UnmatchedPath(
                path=changed_path,
                reason=ownership.reason or "no owning doc found",
                candidates=[_doc_ref(node) for node in ownership.candidates],
            )
        )

    pending = [
        _PendingResult(
            node=group.node,
            inputs=tuple(sorted(group.inputs)),
            source_claims=tuple(sorted(group.source_claims)),
            doc_co_changed=group.node.path.as_posix() in changed_set,
        )
        for group in sorted(groups.values(), key=lambda g: g.node.path.as_posix())
    ]
    unmatched.sort(key=lambda item: item.path)
    return pending, unmatched


def _declared_test_owners(graph: DocGraph) -> dict[str, tuple[DocNode, ...]]:
    owners: dict[str, list[DocNode]] = {}
    for node in graph.nodes.values():
        for test_path in node.frontmatter.tests:
            owners.setdefault(test_path, []).append(node)
    return {
        path: tuple(sorted(nodes, key=lambda item: item.path.as_posix()))
        for path, nodes in owners.items()
    }


def _existing_repo_relative(repo_root: Path, raw_path: Path) -> Path:
    absolute = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = absolute.resolve()
    if not resolved.exists():
        raise ContextError(f"path does not exist: {raw_path}", code=1)
    try:
        rel = resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ContextError(f"path is outside the repo: {raw_path}", code=2) from exc
    return Path(PurePosixPath(*rel.parts))


def _node_matches_topic(node: DocNode, query_lower: str) -> bool:
    haystack = [
        node.id,
        node.frontmatter.title,
        node.path.as_posix(),
        *node.frontmatter.describes,
        *node.frontmatter.tests,
    ]
    return any(query_lower in item.lower() for item in haystack)


def _claim_specs(graph: DocGraph) -> tuple[_ClaimSpec, ...]:
    return tuple(
        _ClaimSpec(
            node=node,
            pattern=pattern,
            score=specificity(pattern),
            spec=GitIgnoreSpec.from_lines([pattern]),
        )
        for node in graph.nodes.values()
        for pattern in node.frontmatter.describes
    )


def _ownership_for_source_path(
    source_path: str,
    claim_specs: Iterable[_ClaimSpec],
) -> _Ownership:
    claims: list[_ClaimSpec] = []
    for claim in claim_specs:
        if claim.spec.match_file(source_path):
            claims.append(claim)

    if not claims:
        return _Ownership(
            node=None,
            pattern=None,
            candidates=(),
            reason="no owning doc found",
        )

    top_score = max(claim.score for claim in claims)
    top_claims = sorted(
        [claim for claim in claims if claim.score == top_score],
        key=lambda claim: claim.node.path.as_posix(),
    )
    if len(top_claims) > 1:
        return _Ownership(
            node=None,
            pattern=None,
            candidates=tuple(claim.node for claim in top_claims),
            reason="ambiguous ownership",
        )

    claim = top_claims[0]
    return _Ownership(
        node=claim.node,
        pattern=claim.pattern,
        candidates=(claim.node,),
        reason=None,
    )


def _git_changed_paths(repo_root: Path) -> list[str]:
    try:
        return working_tree_changed_paths(repo_root)
    except GitChangesError as exc:
        raise ContextError(str(exc), code=1) from exc


def _run_deterministic_checks(
    config: IrminsulConfig,
    graph: DocGraph,
    profile: ContextProfile,
) -> list[Finding]:
    if profile == "hard":
        selected: list[tuple[str, Registry]] = [
            (name, HARD_REGISTRY) for name in config.checks.hard
        ]
    elif profile == "configured":
        selected = [
            *[(name, HARD_REGISTRY) for name in config.checks.hard],
            *[(name, SOFT_REGISTRY) for name in config.checks.soft_deterministic],
        ]
    elif profile == "all-available":
        selected = [
            *[(name, HARD_REGISTRY) for name in HARD_REGISTRY],
            *[(name, SOFT_REGISTRY) for name in SOFT_REGISTRY],
        ]
    else:
        raise ContextError(f"unknown context profile: {profile}", code=2)

    findings: list[Finding] = []
    for check_name, registry in selected:
        cls = registry.get(check_name)
        if cls is None:
            continue
        findings.extend(cls().run(graph))
    return sort_findings(findings)


def _build_result(
    graph: DocGraph,
    pending: _PendingResult,
    all_findings: list[Finding],
    *,
    include_active_changes: bool = False,
) -> ContextResult:
    node = pending.node
    source_claims = list(pending.source_claims) or list(node.frontmatter.describes)
    relevant_findings = _relevant_findings(all_findings, node, pending.inputs)
    return ContextResult(
        input=list(pending.inputs),
        owner=_doc_ref(node),
        source_claims=_unique(source_claims),
        entrypoint=node.frontmatter.describes[0] if node.frontmatter.describes else None,
        tests=list(node.frontmatter.tests),
        depends_on=[
            _doc_ref(graph.nodes[doc_id])
            for doc_id in sorted(node.frontmatter.depends_on)
            if doc_id in graph.nodes
        ],
        depends_on_missing=sorted(
            doc_id for doc_id in node.frontmatter.depends_on if doc_id not in graph.nodes
        ),
        depended_on_by=[
            _doc_ref(graph.nodes[doc_id])
            for doc_id in sorted(graph.inbound_strong.get(node.id, set()))
            if doc_id in graph.nodes
        ],
        findings=[_finding_summary(finding) for finding in relevant_findings],
        hints=_hints(node, relevant_findings),
        active_changes=_active_changes(graph, node) if include_active_changes else [],
        doc_co_changed=pending.doc_co_changed,
    )


def _active_changes(graph: DocGraph, owner: DocNode) -> list[ActiveChange]:
    out: list[ActiveChange] = []
    for node in sorted(graph.nodes.values(), key=lambda item: item.path.as_posix()):
        state = node.frontmatter.rfc_state
        if state is None or canonical_rfc_state(state) not in {
            RfcStateEnum.draft,
            RfcStateEnum.accepted,
        }:
            continue
        if owner.id not in (node.frontmatter.affects or []):
            continue
        section = graph.requirements.get(node.id)
        requirements = (
            [RequirementRef(id=item.req_id, title=item.title) for item in section.requirements]
            if section is not None
            else []
        )
        out.append(
            ActiveChange(
                id=node.id,
                title=node.frontmatter.title,
                path=node.path.as_posix(),
                state=canonical_rfc_state(state).value,
                requirements=requirements,
            )
        )
    return out


def _workflow_validation(
    config: IrminsulConfig,
    findings: list[Finding],
    profile: ContextProfile,
) -> WorkflowValidation:
    hard_names = set(HARD_REGISTRY) if profile == "all-available" else set(config.checks.hard)
    hard_findings = [finding for finding in findings if finding.check in hard_names]
    errors = sum(finding.severity.value == "error" for finding in hard_findings)
    warnings = sum(finding.severity.value == "warning" for finding in hard_findings)
    return WorkflowValidation(
        hard_checks_passed=errors == 0,
        errors=errors,
        warnings=warnings,
    )


def _workflow_next_actions(
    workflow: WorkflowStage,
    results: list[ContextResult],
    unmatched: list[UnmatchedPath],
    validation: WorkflowValidation | None,
    *,
    has_unowned_source: bool,
) -> list[NextAction]:
    actions: list[NextAction] = []

    active_changes: dict[str, tuple[ActiveChange, set[str]]] = {}
    for result in results:
        for change in result.active_changes:
            entry = active_changes.setdefault(change.id, (change, set()))
            entry[1].add(result.owner.id)
    for change_id in sorted(active_changes):
        change, owner_ids = active_changes[change_id]
        sorted_owners = sorted(owner_ids)
        if len(sorted_owners) == 1:
            relationship = f"component '{sorted_owners[0]}'"
        else:
            relationship = "components " + ", ".join(f"'{owner_id}'" for owner_id in sorted_owners)
        actions.append(
            NextAction(
                command=f"irminsul change status {change.id}",
                reason=f"Active RFC explicitly affects {relationship}.",
            )
        )

    if unmatched and has_unowned_source:
        actions.append(
            NextAction(
                command="irminsul list undocumented --all",
                reason="One or more input paths have no deterministic owner.",
            )
        )

    if workflow == "after-edit" and validation is not None and not validation.hard_checks_passed:
        actions.append(
            NextAction(
                command="irminsul check --profile hard",
                reason="The repository hard gate has errors to resolve.",
            )
        )

    if workflow == "after-edit":
        for result in results:
            if result.doc_co_changed:
                continue
            actions.append(
                NextAction(
                    command=f"irminsul context {result.owner.path}",
                    reason=f"Owning document '{result.owner.id}' was not updated in this change.",
                )
            )

    if workflow == "before-edit":
        actions.append(
            NextAction(
                command="irminsul context --after-edit",
                reason="Validate the working tree and affected repository knowledge after editing.",
            )
        )

    return _unique_actions(actions)


def _has_unowned_source(
    repo_root: Path,
    config: IrminsulConfig,
    unmatched: Iterable[UnmatchedPath],
) -> bool:
    prefixes = source_root_prefixes(repo_root, config.paths.source_roots)
    return any(is_source_path(item.path, prefixes) for item in unmatched)


def _unique_actions(actions: Iterable[NextAction]) -> list[NextAction]:
    seen: set[str] = set()
    out: list[NextAction] = []
    for action in actions:
        if action.command in seen:
            continue
        seen.add(action.command)
        out.append(action)
    return out


def _relevant_findings(
    findings: list[Finding],
    node: DocNode,
    inputs: Iterable[str],
) -> list[Finding]:
    input_paths = set(inputs)
    relevant_paths = {node.path.as_posix(), *input_paths}
    out: list[Finding] = []
    for finding in findings:
        finding_path = finding.path.as_posix() if finding.path else None
        if finding.doc_id == node.id:
            out.append(finding)
            continue
        if finding_path in relevant_paths:
            out.append(finding)
            continue
    return out


def _hints(node: DocNode, findings: list[Finding]) -> list[str]:
    hints = ["irminsul check --profile hard"]
    return _unique(hints)


def _doc_ref(node: DocNode) -> DocRef:
    return DocRef(
        id=node.id,
        title=node.frontmatter.title,
        path=node.path.as_posix(),
        status=node.frontmatter.status.value,
        audience=node.frontmatter.audience.value,
        tier=node.frontmatter.tier,
    )


def _finding_summary(finding: Finding) -> FindingSummary:
    return FindingSummary(
        check=finding.check,
        severity=finding.severity.value,
        message=finding.message,
        path=finding.path.as_posix() if finding.path else None,
        doc_id=finding.doc_id,
        line=finding.line,
        suggestion=finding.suggestion,
    )


def _report_to_dict(report: ContextReport) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": report.version,
        "mode": report.mode,
        "results": [
            _result_to_dict(result, include_workflow=report.workflow is not None)
            for result in report.results
        ],
        "unmatched": [_unmatched_to_dict(item) for item in report.unmatched],
    }
    if report.workflow is not None:
        payload["workflow"] = report.workflow
        payload["validation"] = (
            _validation_to_dict(report.validation) if report.validation is not None else None
        )
        payload["next_actions"] = [_next_action_to_dict(action) for action in report.next_actions]
    return payload


def _result_to_dict(
    result: ContextResult,
    *,
    include_workflow: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "input": result.input,
        "owner": _doc_ref_to_dict(result.owner),
        "source_claims": result.source_claims,
        "entrypoint": result.entrypoint,
        "tests": result.tests,
        "depends_on": [_doc_ref_to_dict(doc) for doc in result.depends_on],
        "depends_on_missing": result.depends_on_missing,
        "depended_on_by": [_doc_ref_to_dict(doc) for doc in result.depended_on_by],
        "findings": [_finding_to_dict(finding) for finding in result.findings],
        "hints": result.hints,
        "doc_co_changed": result.doc_co_changed,
    }
    if include_workflow:
        payload["active_changes"] = [
            _active_change_to_dict(change) for change in result.active_changes
        ]
    return payload


def _active_change_to_dict(change: ActiveChange) -> dict[str, object]:
    return {
        "id": change.id,
        "title": change.title,
        "path": change.path,
        "state": change.state,
        "requirements": [
            {"id": requirement.id, "title": requirement.title}
            for requirement in change.requirements
        ],
    }


def _validation_to_dict(validation: WorkflowValidation) -> dict[str, object]:
    return {
        "hard_checks_passed": validation.hard_checks_passed,
        "errors": validation.errors,
        "warnings": validation.warnings,
    }


def _next_action_to_dict(action: NextAction) -> dict[str, str]:
    return {"command": action.command, "reason": action.reason}


def _unmatched_to_dict(item: UnmatchedPath) -> dict[str, object]:
    return {
        "path": item.path,
        "reason": item.reason,
        "candidates": [_doc_ref_to_dict(doc) for doc in item.candidates],
    }


def _doc_ref_to_dict(doc: DocRef) -> dict[str, object]:
    return {
        "id": doc.id,
        "title": doc.title,
        "path": doc.path,
        "status": doc.status,
        "audience": doc.audience,
        "tier": doc.tier,
    }


def _finding_to_dict(finding: FindingSummary) -> dict[str, object]:
    return {
        "check": finding.check,
        "severity": finding.severity,
        "message": finding.message,
        "path": finding.path,
        "doc_id": finding.doc_id,
        "line": finding.line,
        "suggestion": finding.suggestion,
    }


def _format_result(result: ContextResult, *, include_workflow: bool = False) -> list[str]:
    lines = [
        f"owner: {result.owner.id} ({result.owner.path})",
        f"  title: {result.owner.title}",
        f"  input: {_format_list(result.input)}",
        f"  source claims: {_format_list(result.source_claims)}",
        f"  entrypoint: {result.entrypoint or '-'}",
        f"  tests: {_format_list(result.tests)}",
        f"  depends_on: {_format_doc_refs(result.depends_on, result.depends_on_missing)}",
        f"  depended-on-by: {_format_doc_refs(result.depended_on_by, [])}",
    ]
    if include_workflow:
        if result.active_changes:
            lines.append("  active changes:")
            for change in result.active_changes:
                lines.append(f"    {change.id} [{change.state}] ({change.path})")
                requirement_ids = [
                    requirement.id or requirement.title for requirement in change.requirements
                ]
                lines.append(f"      requirements: {_format_list(requirement_ids)}")
        else:
            lines.append("  active changes: -")
    if not result.doc_co_changed:
        lines.append("  co-change: owning doc not updated in this change")
    if result.findings:
        lines.append("  findings:")
        for finding in result.findings:
            location = finding.path or "<repo>"
            if finding.line is not None:
                location = f"{location}:{finding.line}"
            lines.append(f"    [{finding.severity}/{finding.check}] {location}: {finding.message}")
            if finding.suggestion:
                lines.append(f"      suggestion: {finding.suggestion}")
    else:
        lines.append("  findings: (none)")
    lines.append(f"  hints: {_format_list(result.hints)}")
    return lines


def _format_list(values: Iterable[str]) -> str:
    items = list(values)
    return ", ".join(items) if items else "-"


def _format_doc_refs(docs: Iterable[DocRef], missing: Iterable[str]) -> str:
    values = [f"{doc.id} ({doc.path})" for doc in docs]
    values.extend(f"{doc_id} (missing)" for doc_id in missing)
    return _format_list(values)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
