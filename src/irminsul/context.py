"""Runtime context lookup for agents and contributors."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from pathspec import GitIgnoreSpec

from irminsul.checks import (
    REGISTRY,
    Check,
    Finding,
    fix_commands,
    sort_findings,
)
from irminsul.checks.globs import (
    external_display_for_path,
    is_configured_source_path,
    resolve_display_path,
)
from irminsul.checks.links import resolve_target_path
from irminsul.checks.pipeline import run_check
from irminsul.checks.uniqueness import specificity
from irminsul.config import IrminsulConfig, in_layer
from irminsul.declared_tests import governed_as_test, matching_paths
from irminsul.docgraph import DocGraph, DocNode, build_graph
from irminsul.frontmatter import ClaimRelationEnum, RfcStateEnum
from irminsul.git.changes import GitChangesError, working_tree_changed_paths

ContextMode = Literal["path", "topic", "changed"]
ContextProfile = Literal["enabled", "all-available"]
WorkflowStage = Literal["before-edit", "after-edit"]
#: `not_run` is not a third kind of failure — it says the question was never put, and it
#: exists so that "we did not look" cannot be read as "we looked and it was fine".
ValidationState = Literal["not_run", "passed", "failed"]
ContentCategory = Literal["owner", "boundary", "claims", "requirements", "dependencies"]

CONTENT_CATEGORY_ORDER: tuple[ContentCategory, ...] = (
    "owner",
    "boundary",
    "claims",
    "requirements",
    "dependencies",
)
DEFAULT_WORKFLOW_CONTENT: tuple[ContentCategory, ...] = (
    "owner",
    "boundary",
    "claims",
    "requirements",
)
#: The one section excerpted beyond the doc's opening block. A component doc states what
#: it does in its first paragraph and what it deliberately does *not* do here, and the
#: second is what an agent about to add behaviour needs — `docgraph.md` says it does not
#: parse source or infer semantics only under this heading, so a packet without it showed
#: nothing about the boundary being crossed.
_BOUNDARY_HEADING = "scope & limitations"
_CLAIM_REF_RE = re.compile(r"claim:([A-Za-z0-9_.-]+)")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
_MAX_CONTENT_EXCERPTS = 8
#: How many active RFCs a packet names before it starts counting instead.
#: The list is the one part of the packet that grows with the repository rather than
#: with the change: at 1000 RFCs on one component it was 98.8% of the output, a flat
#: unranked list plus one generated next action each. Naming a few and counting the
#: rest keeps the packet readable and, unlike printing all of them, is honest about
#: being a selection. Claim reviews are deliberately *not* capped — they are the
#: obligations a reader must answer, not supporting material.
_MAX_ACTIVE_CHANGES = 8
_MAX_EXCERPT_LINES = 20
_MAX_EXCERPT_CHARS = 1_200


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


@dataclass(frozen=True)
class FindingSummary:
    check: str
    code: str
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
class ActiveChanges:
    """The RFCs named for one owner, and which ones did not fit.

    `omitted` is never inferred from the list's length — a reader cannot tell a complete
    short list from a truncated one, and this packet is read by agents that will act on
    what it says.

    `omitted_ids` names them, because a count is not retrievable. This used to be a count
    plus `retrieve: irminsul list lifecycle`, and that command lists lifecycle findings
    and the accepted backlog: an omitted *draft* — half of what is eligible here — appears
    in neither, so the packet named a command that did not show the rest. An id costs a
    few bytes, which is what the bound is spending, and it is what `retrieve` now takes.
    """

    shown: list[ActiveChange]
    omitted: int = 0
    omitted_ids: list[str] = field(default_factory=list)
    retrieve: str | None = None


@dataclass(frozen=True)
class RepositoryValidation:
    """What the checks said about the whole tree.

    `not_run` carries no counts. A zero there would read as "nothing is wrong" when the
    truth is "nothing was asked", and that is the shape of a false green.
    """

    state: ValidationState
    errors: int | None = None
    warnings: int | None = None


@dataclass(frozen=True)
class ChangeValidation:
    """What this edit introduced, measured against a baseline.

    `not_run` when no baseline could be trusted — `reason` says which — and the
    repository verdict then stands on its own. The comparison is never guessed: a branch
    whose commits are already in HEAD has no baseline in HEAD, so that case reports
    `not_run` rather than a reassuring zero.
    """

    state: ValidationState
    new_errors: int | None = None
    baseline: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class WorkflowValidation:
    """The two verdicts a workflow stage reaches, which answer different questions.

    `repository` is the tree as it stands, legacy violations included. `change` is what
    this edit added to it. An agent is accountable for the second and needs to see the
    first, so neither is folded into the other.
    """

    repository: RepositoryValidation
    change: ChangeValidation


@dataclass(frozen=True)
class NextAction:
    command: str
    reason: str


@dataclass(frozen=True)
class ContentExcerpt:
    category: ContentCategory
    doc_id: str
    path: str
    title: str
    text: str
    reason: str
    truncated: bool


@dataclass(frozen=True)
class ContextContent:
    included: list[ContentExcerpt]
    omitted: dict[str, int]


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
    #: `None` when this run did not execute the checks, which is not the same as their
    #: having found nothing. `before-edit` leaves it `None`.
    findings: list[FindingSummary] | None
    hints: list[str]
    active_changes: ActiveChanges = field(default_factory=lambda: ActiveChanges(shown=[]))
    content: ContextContent | None = None
    doc_co_changed: bool = True


@dataclass(frozen=True)
class GoverningClaim:
    """A claim whose evidence names a path, and the doc that declares it."""

    doc: DocRef
    claim_id: str
    relation: str
    claim: str


@dataclass(frozen=True)
class UnmatchedPath:
    path: str
    reason: str
    candidates: list[DocRef]
    governed_by: list[GoverningClaim] = field(default_factory=list)


@dataclass(frozen=True)
class ClaimReview:
    """A `governs-evidence` claim whose evidence the paths in hand include.

    A request to a reader, not a finding: nothing here says the claim is broken, and
    nothing mechanical could. What it says is that the change reached the code a
    contract is written against, so somebody has to decide whether the contract still
    holds — a question `check` exiting 0 does not answer.
    """

    doc: DocRef
    claim_id: str
    relation: str
    claim: str
    evidence: list[str]
    decisions: list[DocRef]
    tests: list[str]
    question: str


@dataclass(frozen=True)
class ContextReport:
    version: int
    mode: ContextMode
    results: list[ContextResult]
    unmatched: list[UnmatchedPath]
    workflow: WorkflowStage | None = None
    validation: WorkflowValidation | None = None
    next_actions: list[NextAction] = field(default_factory=list)
    claim_reviews: list[ClaimReview] = field(default_factory=list)


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
    profile: ContextProfile = "enabled",
    workflow: WorkflowStage | None = None,
    content_categories: Iterable[ContentCategory] | None = None,
    base_ref: str | None = None,
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

    if content_categories is None:
        categories = DEFAULT_WORKFLOW_CONTENT if workflow is not None else ()
        include_content = workflow is not None
    else:
        categories = _normalize_content_categories(content_categories)
        include_content = True

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

    # Topic mode's inputs are query terms, not paths, so it has no subject files.
    subjects: set[str] = set()
    if mode != "topic":
        subjects = {path for item in pending for path in item.inputs}
        subjects.update(item.path for item in unmatched)
    claim_reviews = claim_reviews_for_paths(graph, subjects, after_change=mode == "changed")
    reviewed_by_doc: dict[str, set[str]] = {}
    for review in claim_reviews:
        reviewed_by_doc.setdefault(review.doc.path, set()).add(review.claim_id)

    # before-edit is a retrieval step: it names the docs, claims and tests to read before
    # touching anything, and a full check pass over the whole tree tells it nothing about
    # a file not yet edited. It was 97% of the command's cost and gated nothing.
    run_checks = workflow != "before-edit" and (pending or workflow is not None)
    findings = _run_deterministic_checks(config, graph, profile) if run_checks else None
    include_workflow = workflow is not None
    results = [
        _build_result(
            graph,
            item,
            findings,
            profile=profile,
            include_active_changes=include_workflow,
            content_categories=categories if include_content else None,
            reviewed_claims=frozenset(reviewed_by_doc.get(item.node.path.as_posix(), ())),
        )
        for item in pending
    ]
    validation = (
        _workflow_validation(
            repo_root, config, findings, profile, workflow=workflow, base_ref=base_ref
        )
        if workflow is not None
        else None
    )
    next_actions = (
        _workflow_next_actions(
            workflow,
            results,
            unmatched,
            validation,
            has_unowned_source=_has_unowned_source(repo_root, config, unmatched),
            claim_reviews=claim_reviews,
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
        claim_reviews=claim_reviews,
    )


def context_report_should_fail(report: ContextReport) -> bool:
    """Whether the CLI should return non-zero after printing a report.

    After an edit the edit-specific signal is what this change introduced, so a sound
    change comparison decides. Where none could be established the whole-repository
    verdict decides instead — the safe existing behaviour, rather than a silent success.
    A stage that ran no checks never fails on validation: it established nothing, and
    exit 0 there means the packet was produced, not that the tree is clean.
    """
    validation = report.validation
    if report.workflow == "after-edit" and validation is not None:
        if validation.change.state != "not_run":
            return validation.change.state == "failed"
        return validation.repository.state == "failed"
    return report.mode == "path" and not report.results


def context_report_to_json(report: ContextReport) -> str:
    return json.dumps(_report_to_dict(report), indent=2)


def parse_content_categories(raw: str) -> tuple[ContentCategory, ...]:
    values = [value.strip().lower() for value in raw.split(",") if value.strip()]
    if not values:
        raise ContextError("--include requires one or more content categories", code=2)
    if "all" in values:
        if len(values) != 1:
            raise ContextError("--include all cannot be combined with other categories", code=2)
        return CONTENT_CATEGORY_ORDER
    if "none" in values:
        if len(values) != 1:
            raise ContextError("--include none cannot be combined with other categories", code=2)
        return ()
    return _normalize_content_categories(values)


def _normalize_content_categories(
    categories: Iterable[str],
) -> tuple[ContentCategory, ...]:
    selected = set(categories)
    unknown = sorted(selected - set(CONTENT_CATEGORY_ORDER))
    if unknown:
        expected = ", ".join(CONTENT_CATEGORY_ORDER)
        raise ContextError(
            f"unknown --include categories: {', '.join(unknown)}; expected {expected}",
            code=2,
        )
    return tuple(category for category in CONTENT_CATEGORY_ORDER if category in selected)


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

    reviewed = {(review.doc.path, review.claim_id) for review in report.claim_reviews}
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
            for governing in item.governed_by:
                if (governing.doc.path, governing.claim_id) in reviewed:
                    continue  # the claims-to-review block below says more about it
                lines.append(
                    f"    governed by {governing.claim_id} ({governing.relation}) "
                    f"in {governing.doc.path}"
                )
                lines.append(f"      {governing.claim}")
        if report.workflow is None:
            lines.append("  hint: irminsul list undocumented --all")

    if report.claim_reviews:
        if lines:
            lines.append("")
        header = (
            "Claims to review — this change touched their evidence:"
            if report.workflow == "after-edit"
            else "Claims to read before editing these paths:"
        )
        lines.append(header)
        for review in report.claim_reviews:
            lines.append(f"  {review.claim_id} ({review.relation}) in {review.doc.path}")
            lines.append(f"    claim: {review.claim}")
            lines.append(f"    evidence in hand: {', '.join(review.evidence)}")
            if review.decisions:
                decided = ", ".join(doc.path for doc in review.decisions)
                lines.append(f"    decided in: {decided}")
            if review.tests:
                lines.append(f"    declared tests: {', '.join(review.tests)}")
            lines.append(f"    question: {review.question}")
        lines.append("  This is a question for you, not a finding: no check can answer it.")

    if report.workflow is not None:
        if lines:
            lines.append("")
        validation = report.validation
        if validation is not None:
            lines.extend(_validation_lines(validation))
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
    source_roots = graph.config.paths.source_roots if graph.config is not None else []
    rel = _existing_repo_relative(repo_root, target_path, source_roots)
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
            governed_by=_governing_claims(graph, display),
        )
    ]


def _pending_for_topic(graph: DocGraph, topic: str) -> list[_PendingResult]:
    query = topic.strip()
    if not query:
        raise ContextError("topic query cannot be empty", code=2)

    terms = tuple(query.lower().split())
    normalized_query = " ".join(terms)
    normalized_phrase = _normalize_topic_phrase(normalized_query) or normalized_query
    matches = [
        match
        for node in graph.nodes.values()
        if (match := _match_topic(node, terms, normalized_phrase)) is not None
    ]
    if not matches:
        return []

    matches.sort(
        key=lambda match: (
            0 if _normalize_topic_phrase(match.node.id) == normalized_phrase else 1,
            0 if match.exact_phrase else 1,
            -match.fields_hit,
            match.node.path.as_posix(),
            match.node.frontmatter.title.lower(),
            match.node.id,
        )
    )
    return [
        _PendingResult(
            node=match.node,
            inputs=(query,),
            source_claims=tuple(match.node.frontmatter.describes),
        )
        for match in matches
    ]


def _pending_for_changed(
    repo_root: Path,
    graph: DocGraph,
) -> tuple[list[_PendingResult], list[UnmatchedPath]]:
    groups: dict[str, _ChangedGroup] = {}
    unmatched: list[UnmatchedPath] = []
    claim_specs = _claim_specs(graph)

    changed_paths = _git_changed_paths(repo_root)
    changed_set = set(changed_paths)
    test_owners = _declared_test_routes(graph, changed_paths)

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
                governed_by=_governing_claims(graph, changed_path),
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


def _declared_test_routes(
    graph: DocGraph, changed_paths: list[str]
) -> dict[str, tuple[DocNode, ...]]:
    """Which docs each changed path reaches through a declared test reference.

    Matched with the shared resolver, so a directory or glob entry routes the way it
    matches everywhere else; comparing raw strings meant `tests/` routed nothing at all.
    Routing is not ownership — a doc that only recommends a shared test still appears,
    because whoever edits that test wants the context of everyone who runs it.
    """
    assert graph.config is not None
    routes: dict[str, list[DocNode]] = {}
    for node in graph.nodes.values():
        for path in matching_paths(node.frontmatter.effective_recommended_tests, changed_paths):
            # Only a file the test policy governs may be routed this way. Recommendations
            # are allowed to be broad, so `recommended_tests: ["src/"]` would otherwise
            # make every changed source file under it read as owned by this doc, and a file
            # nothing describes would stop being reported as unmatched — a recommendation
            # quietly reclassifying ordinary source.
            if governed_as_test(path, graph.config):
                routes.setdefault(path, []).append(node)
    return {
        path: tuple(sorted(nodes, key=lambda item: item.path.as_posix()))
        for path, nodes in routes.items()
    }


def _existing_repo_relative(repo_root: Path, raw_path: Path, source_roots: list[str]) -> Path:
    """The display spelling of an existing file, or a `ContextError`.

    A path inside the invocation root answers repo-relative, the way it always
    has. Failing that, the value is read as a display spelling — the one
    `describes:` and `claims[].evidence` speak — which is how a source file in
    a sibling code repo is named: with `source_roots = ["../code/src"]`,
    `workspace/code/src/app/main.py` is `app/main.py`. Without this the layout
    had no spelling at all for its own source files: the `../code/...` form is
    outside the repo and refused, and the display form did not exist on disk
    under `repo_root`.

    The mirror also holds: an existing file under a configured external root —
    `../code/src/app/main.py`, the spelling a shell tab-completes — maps to
    its display spelling instead of being refused, the encode direction of the
    same round trip. Only a path that neither lies in the repo nor maps to a
    display the tool speaks is refused as outside the repo.
    """
    absolute = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = absolute.resolve()
    if resolved.exists():
        try:
            rel = resolved.relative_to(repo_root.resolve())
        except ValueError as exc:
            display_spelling = external_display_for_path(repo_root, source_roots, resolved)
            if display_spelling is not None:
                return Path(PurePosixPath(display_spelling))
            raise ContextError(f"path is outside the repo: {raw_path}", code=2) from exc
        return Path(PurePosixPath(*rel.parts))

    display = PurePosixPath(raw_path.as_posix())
    if not raw_path.is_absolute() and resolve_display_path(repo_root, source_roots, str(display)):
        return Path(display)
    raise ContextError(f"path does not exist: {raw_path}", code=1)


@dataclass(frozen=True)
class _TopicMatch:
    node: DocNode
    exact_phrase: bool
    fields_hit: int


def _topic_haystack(node: DocNode) -> dict[str, str]:
    return {
        "id": node.id.lower(),
        "title": node.frontmatter.title.lower(),
        "path": node.path.as_posix().lower(),
        "describes": " ".join(node.frontmatter.describes).lower(),
        "tests": " ".join(node.frontmatter.effective_recommended_tests).lower(),
        "tags": " ".join(node.frontmatter.tags).lower(),
        "summary": (node.frontmatter.summary or "").lower(),
    }


def _normalize_topic_phrase(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.lower()).strip()


def _match_topic(
    node: DocNode, terms: tuple[str, ...], normalized_phrase: str
) -> _TopicMatch | None:
    haystack = _topic_haystack(node)
    fields_hit: set[str] = set()
    for term in terms:
        term_fields = [field for field, text in haystack.items() if term in text]
        if not term_fields:
            return None
        fields_hit.update(term_fields)
    exact_phrase = any(
        normalized_phrase in _normalize_topic_phrase(text) for text in haystack.values()
    )
    return _TopicMatch(node=node, exact_phrase=exact_phrase, fields_hit=len(fields_hit))


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


def _governing_claims(graph: DocGraph, display: str) -> list[GoverningClaim]:
    """Claims whose `evidence` names this path, ordered by declaring doc then claim id.

    A file outside every `describes:` glob has no owning doc, and `action.yml` is one:
    it sits above `source_roots`, so the walk never offers it and no glob can claim it.
    The repository still says something about it — `architecture/overview.md` carries a
    `governs-evidence` claim citing it — and that is what an agent about to edit it needs.
    Reported as governance rather than ownership, because a claim does not own a file.
    """
    out: list[GoverningClaim] = []
    for node in graph.nodes.values():
        for claim in node.frontmatter.claims:
            if display not in claim.evidence:
                continue
            out.append(
                GoverningClaim(
                    doc=_doc_ref(node),
                    claim_id=claim.id,
                    relation=claim.relation.value,
                    claim=claim.claim,
                )
            )
    return sorted(out, key=lambda item: (item.doc.path, item.claim_id))


def claim_reviews_for_paths(
    graph: DocGraph, paths: Iterable[str], *, after_change: bool = False
) -> list[ClaimReview]:
    """Claims a reader has to settle, whose evidence any of `paths` names.

    `governs-evidence` and `review-on-divergence`, not `follows-evidence`. The first two
    are the relations where a change to the code leaves a question open: under one the
    claim wins so the code is suspect, under the other neither wins and someone decides.
    Under `follows-evidence` the code wins outright, so the edit settles the question
    instead of raising it and a prompt would be noise.

    Membership is the same exact-string test `evidence:` is authored in, so a claim
    citing a file this change touched is reported whether or not the declaring doc owns
    that file, and whether or not the doc changed too — editing prose elsewhere in a doc
    is not evidence that anyone re-read the claim in it.
    """
    wanted = set(paths)
    if not wanted:
        return []
    out: list[ClaimReview] = []
    for node in graph.nodes.values():
        for claim in node.frontmatter.claims:
            if claim.relation is ClaimRelationEnum.follows_evidence:
                continue
            touched = sorted(wanted.intersection(claim.evidence))
            if not touched:
                continue
            out.append(
                ClaimReview(
                    doc=_doc_ref(node),
                    claim_id=claim.id,
                    relation=claim.relation.value,
                    claim=claim.claim,
                    evidence=touched,
                    decisions=_claim_decisions(graph, node, claim.id),
                    tests=list(node.frontmatter.effective_recommended_tests),
                    question=_claim_question(touched, claim.relation, after_change=after_change),
                )
            )
    return sorted(out, key=lambda item: (item.doc.path, item.claim_id))


def _claim_question(
    evidence: Iterable[str], relation: ClaimRelationEnum, *, after_change: bool
) -> str:
    """The claim's own sentence, turned back on the files in hand.

    The sentence is quoted beside this rather than summarized into it. A generated
    paraphrase would ask about the topic instead of the claim — for
    `context-is-stateless` it would ask about caching, which the same document
    explicitly permits — while the authored sentence already says which state is
    forbidden and for whom.

    What differs by relation is who the question is addressed to. A contract asks whether
    the code still obeys it; a model asks which of the two is now wrong, because under
    `review-on-divergence` nothing decides that but a reader.
    """
    listed = ", ".join(evidence)
    if relation is ClaimRelationEnum.governs_evidence:
        asked = (
            f"does {listed} still satisfy the sentence above"
            if after_change
            else f"will your change leave {listed} satisfying the sentence above"
        )
        return (
            f"{'After this change, ' if after_change else ''}{asked}? "
            "The claim governs its evidence, so if the two disagree the code is what is "
            "wrong; changing the sentence instead is a change of intent."
        )
    asked = (
        f"do {listed} and the sentence above still agree"
        if after_change
        else f"will {listed} and the sentence above still agree"
    )
    return (
        f"{'After this change, ' if after_change else ''}{asked}? "
        "Neither one wins by default here: decide which of the two is now wrong, correct "
        "that one, and say why in the change."
    )


def _claim_decisions(graph: DocGraph, node: DocNode, claim_id: str) -> list[DocRef]:
    """Decision docs linked from the paragraphs carrying this claim's `claim:` marker.

    The marker is what ties a sentence in the body to a frontmatter claim, so the links
    beside it are the ones its author put there. A claim with no marker reports no
    decision rather than a guess assembled from the document's other links.
    """
    config = graph.config
    if config is None:
        return []
    found: dict[str, DocRef] = {}
    # By paragraph, not by line: the marker closes the paragraph it belongs to, while the
    # link that decided the claim usually sits a sentence or two earlier in the same one.
    for block in re.split(r"\n\s*\n", node.body):
        if claim_id not in set(_CLAIM_REF_RE.findall(block)):
            continue
        for target in _MARKDOWN_LINK_RE.findall(block):
            resolved = _resolve_doc_link(graph, node, target)
            if resolved is None or not in_layer(config, resolved.path, "decisions"):
                continue
            found.setdefault(resolved.path.as_posix(), _doc_ref(resolved))
    return [found[key] for key in sorted(found)]


def _resolve_doc_link(graph: DocGraph, node: DocNode, target: str) -> DocNode | None:
    link = target.split("#", 1)[0].strip()
    if not link or "://" in link:
        return None
    return graph.by_path.get(resolve_target_path(node, link))


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
    if profile == "enabled":
        selected: list[tuple[str, Registry]] = [(name, REGISTRY) for name in config.checks.enabled]
    elif profile == "all-available":
        selected = [(name, REGISTRY) for name in REGISTRY]
    else:
        raise ContextError(f"unknown context profile: {profile}", code=2)

    from irminsul.checks.pipeline import finish, mandatory_findings

    findings: list[Finding] = []
    for check_name, registry in selected:
        cls = registry.get(check_name)
        if cls is None:
            continue
        findings.extend(run_check(cls, graph))
    # `--after-edit` is the step the agent protocol puts between editing and committing, and
    # its verdict is what an agent acts on. Assembling the run from the registry alone left
    # out the passes that judge the run, so a corrupt adoption record came back as a clean
    # repository — the ownership checks stay silent about it by design, on the understanding
    # that this pass speaks.
    findings.extend(finish(mandatory_findings(graph, [name for name, _ in selected]), graph))
    return sort_findings(findings)


def _build_result(
    graph: DocGraph,
    pending: _PendingResult,
    all_findings: list[Finding] | None,
    *,
    profile: ContextProfile = "enabled",
    include_active_changes: bool = False,
    content_categories: tuple[ContentCategory, ...] | None = None,
    reviewed_claims: frozenset[str] = frozenset(),
) -> ContextResult:
    node = pending.node
    source_claims = list(pending.source_claims) or list(node.frontmatter.describes)
    relevant_findings = (
        _relevant_findings(all_findings, node, pending.inputs) if all_findings is not None else None
    )
    all_changes = (
        _active_changes(graph, node)
        if include_active_changes
        or (content_categories is not None and "requirements" in content_categories)
        else []
    )
    return ContextResult(
        input=list(pending.inputs),
        owner=_doc_ref(node),
        source_claims=_unique(source_claims),
        entrypoint=node.frontmatter.describes[0] if node.frontmatter.describes else None,
        tests=list(node.frontmatter.effective_recommended_tests),
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
        findings=(
            None
            if relevant_findings is None
            else [_finding_summary(finding) for finding in relevant_findings]
        ),
        hints=[] if relevant_findings is None else _hints(graph, relevant_findings, profile),
        active_changes=_bound_active_changes(all_changes)
        if include_active_changes
        else ActiveChanges(shown=[]),
        content=(
            _build_context_content(graph, node, all_changes, content_categories, reviewed_claims)
            if content_categories is not None
            else None
        ),
        doc_co_changed=pending.doc_co_changed,
    )


def _bound_active_changes(changes: list[ActiveChange]) -> ActiveChanges:
    """The RFCs a packet names, and a count of the ones it does not.

    Ordering is the caller's — doc-path order — so the selection is deterministic rather
    than arbitrary. It is not a relevance ranking and nothing here claims one. The cap
    buys a readable packet; the count buys the thing the uncapped version could not
    express, which is the difference between a complete list and a selection.
    """
    if len(changes) <= _MAX_ACTIVE_CHANGES:
        return ActiveChanges(shown=changes)
    rest = changes[_MAX_ACTIVE_CHANGES:]
    return ActiveChanges(
        shown=changes[:_MAX_ACTIVE_CHANGES],
        omitted=len(rest),
        omitted_ids=[change.id for change in rest],
        retrieve="irminsul change status <rfc-id>",
    )


def _active_changes(graph: DocGraph, owner: DocNode) -> list[ActiveChange]:
    out: list[ActiveChange] = []
    for node in sorted(graph.nodes.values(), key=lambda item: item.path.as_posix()):
        state = node.frontmatter.rfc_state
        if state is None or state not in {
            RfcStateEnum.draft,
            RfcStateEnum.accepted,
        }:
            continue
        updates = {entry.path for entry in node.frontmatter.required_updates or []}
        if (
            owner.id not in (node.frontmatter.affects or [])
            and owner.path.as_posix() not in updates
        ):
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
                state=state.value,
                requirements=requirements,
            )
        )
    return out


def _build_context_content(
    graph: DocGraph,
    owner: DocNode,
    active_changes: list[ActiveChange],
    categories: tuple[ContentCategory, ...],
    reviewed_claims: frozenset[str] = frozenset(),
) -> ContextContent:
    candidates: dict[ContentCategory, list[ContentExcerpt]] = {
        category: [] for category in categories
    }

    if "owner" in candidates:
        excerpt = _document_excerpt(
            owner,
            category="owner",
            reason=f"Owns the requested path through document '{owner.id}'.",
        )
        if excerpt is not None:
            candidates["owner"].append(excerpt)

    if "boundary" in candidates:
        boundary = _boundary_excerpt(owner)
        if boundary is not None:
            candidates["boundary"].append(boundary)

    if "claims" in candidates:
        for claim in owner.frontmatter.claims:
            # A claim queued for review is printed in full there, with its decision,
            # evidence and question. Excerpting it again would ask the same thing twice.
            if claim.id in reviewed_claims:
                continue
            text, truncated = _bound_excerpt(claim.claim)
            if not text:
                continue
            candidates["claims"].append(
                ContentExcerpt(
                    category="claims",
                    doc_id=owner.id,
                    path=owner.path.as_posix(),
                    title=f"Claim {claim.id} ({claim.kind})",
                    text=text,
                    reason="Structured claim declared by the owning document.",
                    truncated=truncated,
                )
            )

    if "requirements" in candidates:
        for change in active_changes:
            section = graph.requirements.get(change.id)
            node = graph.nodes.get(change.id)
            if section is None or node is None:
                continue
            for requirement in section.requirements:
                text, truncated = _bound_excerpt(requirement.text)
                if not text:
                    continue
                label = requirement.req_id or requirement.title
                candidates["requirements"].append(
                    ContentExcerpt(
                        category="requirements",
                        doc_id=node.id,
                        path=node.path.as_posix(),
                        title=f"Requirement {label}: {requirement.title}",
                        text=text,
                        reason=(f"Active RFC '{change.id}' explicitly affects owner '{owner.id}'."),
                        truncated=truncated,
                    )
                )

    if "dependencies" in candidates:
        dependencies = [
            graph.nodes[doc_id] for doc_id in owner.frontmatter.depends_on if doc_id in graph.nodes
        ]
        for dependency in sorted(dependencies, key=lambda item: item.path.as_posix()):
            excerpt = _document_excerpt(
                dependency,
                category="dependencies",
                reason=f"Owning document '{owner.id}' declares depends_on '{dependency.id}'.",
            )
            if excerpt is not None:
                candidates["dependencies"].append(excerpt)

    included: list[ContentExcerpt] = []
    omitted: dict[str, int] = {}
    for category in CONTENT_CATEGORY_ORDER:
        if category not in candidates:
            continue
        available = candidates[category]
        remaining = max(_MAX_CONTENT_EXCERPTS - len(included), 0)
        selected = available[:remaining]
        included.extend(selected)
        omitted[category] = len(available) - len(selected)

    return ContextContent(included=included, omitted=omitted)


def _document_excerpt(
    node: DocNode,
    *,
    category: Literal["owner", "dependencies"],
    reason: str,
) -> ContentExcerpt | None:
    extracted = _first_substantive_block(node.body)
    if extracted is None:
        return None
    heading, raw_text = extracted
    text, truncated = _bound_excerpt(raw_text)
    if not text:
        return None
    return ContentExcerpt(
        category=category,
        doc_id=node.id,
        path=node.path.as_posix(),
        title=heading or node.frontmatter.title,
        text=text,
        reason=reason,
        truncated=truncated,
    )


def _boundary_excerpt(node: DocNode) -> ContentExcerpt | None:
    """The owning doc's `## Scope & Limitations` section, or None when it has none.

    One named section rather than every section: a packet carrying the whole document
    would stop being a map. This is the heading a component doc puts its exclusions under,
    and an agent about to add behaviour needs what the component deliberately does *not*
    do. What the section says is prose to weigh, not a rule — `docgraph.md` states both a
    boundary it keeps and, in the same section, a property nothing enforces.

    A section holding only the scaffold's HTML comment is not an answer, and reading one
    back to an agent dressed as "what the component does not do" is worse than saying
    nothing: `<!-- Describe what this component does NOT do. -->` is a prompt for a person.
    `boundary/unfilled-scope-section` reports it; this returns nothing for it.
    """
    lines = node.body.splitlines()
    start: int | None = None
    end = len(lines)
    level = 0
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped.startswith("#"):
            continue
        hashes = len(stripped) - len(stripped.lstrip("#"))
        title = stripped.lstrip("#").strip()
        if start is None:
            if title.lower() == _BOUNDARY_HEADING:
                start, level = index + 1, hashes
            continue
        if hashes <= level:
            end = index
            break
    if start is None:
        return None
    body = re.sub(r"<!--.*?-->", "", "\n".join(lines[start:end]), flags=re.DOTALL).strip()
    text, truncated = _bound_excerpt(body)
    if not text:
        return None
    return ContentExcerpt(
        category="boundary",
        doc_id=node.id,
        path=node.path.as_posix(),
        title=f"Scope & Limitations ({node.frontmatter.title})",
        text=text,
        reason="What the owning document says this component does not do.",
        truncated=truncated,
    )


def _first_substantive_block(body: str) -> tuple[str | None, str] | None:
    heading: str | None = None
    content: list[str] = []
    in_comment = False
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        if stripped.startswith("#") and stripped.lstrip("#").startswith(" "):
            if content:
                break
            heading = stripped.lstrip("#").strip()
            continue
        if not stripped:
            if content:
                break
            continue
        content.append(raw_line.rstrip())
    if not content:
        return None
    return heading, "\n".join(content)


def _bound_excerpt(text: str) -> tuple[str, bool]:
    normalized = text.strip()
    if not normalized:
        return "", False

    lines = normalized.splitlines()
    selected = lines[:_MAX_EXCERPT_LINES]
    bounded = "\n".join(selected).strip()
    truncated = len(lines) > _MAX_EXCERPT_LINES
    if len(bounded) > _MAX_EXCERPT_CHARS:
        bounded = bounded[: _MAX_EXCERPT_CHARS - 3].rstrip() + "..."
        truncated = True
    return bounded, truncated


def _validation_lines(validation: WorkflowValidation) -> list[str]:
    """Both verdicts, each saying plainly whether it was reached at all."""
    repository = validation.repository
    if repository.state == "not_run":
        lines = ["Repository validation: not run (no checks were executed)"]
    else:
        lines = [
            f"Repository validation: {repository.state} "
            f"({repository.errors} errors, {repository.warnings} warnings)"
        ]
    change = validation.change
    if change.state == "not_run":
        lines.append("Change validation: not run")
        if change.reason:
            lines.append(f"  reason: {change.reason}")
    else:
        lines.append(
            f"Change validation: {change.state} "
            f"({change.new_errors} new errors vs {change.baseline})"
        )
    return lines


_NOT_RUN_BEFORE_EDIT = (
    "before-edit does not run the checks; run `irminsul context --after-edit` once the "
    "edit is made, or `irminsul check` for the tree as it stands"
)


def _workflow_validation(
    repo_root: Path,
    config: IrminsulConfig,
    findings: list[Finding] | None,
    profile: ContextProfile,
    *,
    workflow: WorkflowStage,
    base_ref: str | None,
) -> WorkflowValidation:
    if findings is None:
        return WorkflowValidation(
            repository=RepositoryValidation(state="not_run"),
            change=ChangeValidation(state="not_run", reason=_NOT_RUN_BEFORE_EDIT),
        )
    errors = sum(finding.severity.value == "error" for finding in findings)
    warnings = sum(finding.severity.value == "warning" for finding in findings)
    repository = RepositoryValidation(
        state="passed" if errors == 0 else "failed",
        errors=errors,
        warnings=warnings,
    )
    change = (
        _change_validation(repo_root, config, profile, findings, base_ref)
        if workflow == "after-edit"
        else ChangeValidation(state="not_run", reason=_NOT_RUN_BEFORE_EDIT)
    )
    return WorkflowValidation(repository=repository, change=change)


def _change_validation(
    repo_root: Path,
    config: IrminsulConfig,
    profile: ContextProfile,
    findings: list[Finding],
    base_ref: str | None,
) -> ChangeValidation:
    """What this edit introduced, or why that could not be established.

    The base is checked out into a scratch worktree and the same checks are run over it,
    so "new" means a finding the base run did not produce — not a finding whose file the
    edit happened to touch. Everything that can go wrong here ends as `not_run` with a
    reason, because the one answer this must never give is a zero it did not measure.
    """
    from irminsul.change.report import resolve_change_baseline
    from irminsul.delta import (
        DeltaError,
        base_is_the_working_tree,
        compute_delta,
        pristine_checkout,
        verify_single_repo_topology,
    )

    baseline = resolve_change_baseline(repo_root, base_ref)
    if baseline.changed_paths is None:
        return ChangeValidation(
            state="not_run",
            baseline=baseline.ref,
            reason=(
                "no diff baseline could be resolved; pass --base-ref <ref> or set IRMINSUL_BASE_REF"
            ),
        )
    rev = baseline.ref or "HEAD"
    try:
        verify_single_repo_topology(repo_root, config)
        if base_is_the_working_tree(repo_root, config, rev):
            # HEAD already holds whatever this branch committed, so every finding would
            # count as pre-existing and the answer would be a zero that measured nothing.
            return ChangeValidation(
                state="not_run",
                baseline=rev,
                reason=(
                    f"the tree the checks read is identical to {rev}, so there is nothing "
                    "to compare; pass --base-ref <ref> naming the branch point"
                ),
            )
        with pristine_checkout(repo_root, rev) as base_root:
            base_findings = _run_deterministic_checks(
                config, build_graph(base_root, config, state_root=repo_root), profile
            )
    except DeltaError as exc:
        return ChangeValidation(state="not_run", baseline=rev, reason=str(exc))

    new_errors = sum(
        finding.severity.value == "error" for finding in compute_delta(findings, base_findings).new
    )
    return ChangeValidation(
        state="passed" if new_errors == 0 else "failed",
        new_errors=new_errors,
        baseline=rev,
    )


def _workflow_next_actions(
    workflow: WorkflowStage,
    results: list[ContextResult],
    unmatched: list[UnmatchedPath],
    validation: WorkflowValidation | None,
    *,
    has_unowned_source: bool,
    claim_reviews: list[ClaimReview],
) -> list[NextAction]:
    actions: list[NextAction] = []

    for review in claim_reviews:
        touched = (
            "This change touched evidence"
            if workflow == "after-edit"
            else "These paths are evidence"
        )
        governs = review.relation == ClaimRelationEnum.governs_evidence.value
        named = "governing claim" if governs else "claim"
        settle = (
            "decide whether the claim still holds"
            if governs
            else "decide whether claim and code still agree"
        )
        actions.append(
            NextAction(
                command=f"irminsul context {review.doc.path}",
                reason=(
                    f"{touched} for {named} '{review.claim_id}'; read the document "
                    f"that declares it and {settle}."
                ),
            )
        )

    active_changes: dict[str, tuple[ActiveChange, set[str]]] = {}
    for result in results:
        for change in result.active_changes.shown:
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

    if workflow == "after-edit" and validation is not None:
        if validation.change.state == "failed":
            actions.append(
                NextAction(
                    command="irminsul check",
                    reason="This change introduced errors.",
                )
            )
        elif validation.repository.state == "failed":
            actions.append(
                NextAction(
                    command="irminsul check",
                    reason=(
                        "The repository has errors to resolve; they are not this change's."
                        if validation.change.state == "passed"
                        else "The repository has errors to resolve."
                    ),
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
    return any(is_configured_source_path(repo_root, config, item.path) for item in unmatched)


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


def _hints(
    graph: DocGraph,
    findings: list[Finding],
    profile: ContextProfile,
) -> list[str]:
    """Next commands for this result: remediations first, then the gate.

    Remediations come from the same finding-to-fix mapping the findings surfaces
    use, so a hint is only offered when the check actually harvests a fix for
    that finding. The verification gate stays last because it is the terminal
    step regardless of what precedes it.
    """
    hints = [command for command in fix_commands(findings, graph, profile=profile) if command]
    hints.append("irminsul check")
    return _unique(hints)


def _doc_ref(node: DocNode) -> DocRef:
    return DocRef(
        id=node.id,
        title=node.frontmatter.title,
        path=node.path.as_posix(),
        status=node.frontmatter.status.value,
    )


def _finding_summary(finding: Finding) -> FindingSummary:
    return FindingSummary(
        check=finding.check,
        code=finding.code,
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
        "claim_reviews": [_claim_review_to_dict(review) for review in report.claim_reviews],
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
        "findings": (
            None
            if result.findings is None
            else [_finding_to_dict(finding) for finding in result.findings]
        ),
        "hints": result.hints,
        "doc_co_changed": result.doc_co_changed,
    }
    if include_workflow:
        payload["active_changes"] = {
            "shown": [_active_change_to_dict(change) for change in result.active_changes.shown],
            "omitted": result.active_changes.omitted,
            "omitted_ids": result.active_changes.omitted_ids,
            "retrieve": result.active_changes.retrieve,
        }
    if result.content is not None:
        payload["content"] = _content_to_dict(result.content)
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
    """The two verdicts, plus `checks_passed` for readers written against the old shape.

    That key is emitted only where the checks actually ran, so a reader that still
    consults it gets a KeyError on an unrun stage rather than a `True` it would have read
    as success. It says the same thing as `repository.state`; prefer the latter.
    """
    repository = validation.repository
    change = validation.change
    payload: dict[str, object] = {
        "repository": {
            "state": repository.state,
            "errors": repository.errors,
            "warnings": repository.warnings,
        },
        "change": {
            "state": change.state,
            "new_errors": change.new_errors,
            "baseline": change.baseline,
            "reason": change.reason,
        },
    }
    if repository.state != "not_run":
        payload["checks_passed"] = repository.state == "passed"
    return payload


def _next_action_to_dict(action: NextAction) -> dict[str, str]:
    return {"command": action.command, "reason": action.reason}


def _content_to_dict(content: ContextContent) -> dict[str, object]:
    return {
        "included": [
            {
                "category": excerpt.category,
                "doc_id": excerpt.doc_id,
                "path": excerpt.path,
                "title": excerpt.title,
                "text": excerpt.text,
                "reason": excerpt.reason,
                "truncated": excerpt.truncated,
            }
            for excerpt in content.included
        ],
        "omitted": content.omitted,
    }


def _unmatched_to_dict(item: UnmatchedPath) -> dict[str, object]:
    return {
        "path": item.path,
        "reason": item.reason,
        "candidates": [_doc_ref_to_dict(doc) for doc in item.candidates],
        "governed_by": [
            {
                "doc": _doc_ref_to_dict(governing.doc),
                "claim_id": governing.claim_id,
                "relation": governing.relation,
                "claim": governing.claim,
            }
            for governing in item.governed_by
        ],
    }


def _claim_review_to_dict(review: ClaimReview) -> dict[str, object]:
    return {
        "doc": _doc_ref_to_dict(review.doc),
        "claim_id": review.claim_id,
        "relation": review.relation,
        "claim": review.claim,
        "evidence": review.evidence,
        "decisions": [_doc_ref_to_dict(doc) for doc in review.decisions],
        "tests": review.tests,
        "question": review.question,
    }


def _doc_ref_to_dict(doc: DocRef) -> dict[str, object]:
    return {
        "id": doc.id,
        "title": doc.title,
        "path": doc.path,
        "status": doc.status,
    }


def _finding_to_dict(finding: FindingSummary) -> dict[str, object]:
    return {
        "check": finding.check,
        "code": finding.code,
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
        if result.active_changes.shown:
            lines.append("  active changes:")
            for change in result.active_changes.shown:
                lines.append(f"    {change.id} [{change.state}] ({change.path})")
                requirement_ids = [
                    requirement.id or requirement.title for requirement in change.requirements
                ]
                lines.append(f"      requirements: {_format_list(requirement_ids)}")
            if result.active_changes.omitted:
                lines.append(
                    f"    ... and {result.active_changes.omitted} more: "
                    f"{', '.join(result.active_changes.omitted_ids)}; "
                    f"see `{result.active_changes.retrieve}`"
                )
        else:
            lines.append("  active changes: -")
    if result.content is not None:
        lines.append("  content:")
        if result.content.included:
            for excerpt in result.content.included:
                suffix = " [truncated]" if excerpt.truncated else ""
                lines.append(f"    [{excerpt.category}] {excerpt.title} ({excerpt.path}){suffix}")
                lines.append(f"      reason: {excerpt.reason}")
                lines.extend(f"      {line}" for line in excerpt.text.splitlines())
        else:
            lines.append("    (none)")
        omitted = [
            f"{category}={count}" for category, count in result.content.omitted.items() if count
        ]
        if omitted:
            lines.append(f"    omitted: {', '.join(omitted)}")
    if not result.doc_co_changed:
        lines.append("  co-change: owning doc not updated in this change")
    if result.findings is None:
        lines.append("  findings: not checked (run `irminsul check`)")
    elif result.findings:
        lines.append("  findings:")
        for finding in result.findings:
            location = finding.path or "<repo>"
            if finding.line is not None:
                location = f"{location}:{finding.line}"
            # Same identity convention as `irminsul check`: the bracketed code
            # is what `irminsul explain <code>` accepts; severity stays visible.
            lines.append(f"    {finding.severity}  [{finding.code}] {location}: {finding.message}")
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
