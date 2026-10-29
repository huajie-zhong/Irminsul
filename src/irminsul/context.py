"""Runtime context lookup for agents and contributors."""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

from irminsul.adoption import recorded_debt
from irminsul.checks import Finding, finding_records
from irminsul.checks.change_range import range_of
from irminsul.checks.globs import (
    external_display_for_path,
    is_configured_source_path,
    resolve_display_path,
)
from irminsul.checks.pipeline import CHANGE_PASSES, RunResult
from irminsul.checks.uniqueness import Claim, most_specific_claims, resolve_claims
from irminsul.config import IrminsulConfig, in_layer
from irminsul.declared_tests import governed_as_test, matching_paths
from irminsul.docgraph import ChangeRange, DocGraph, DocNode, build_graph
from irminsul.docgraph_index import headings_of, linked_node, section_lines
from irminsul.errors import UserError
from irminsul.frontmatter import RFC_OPEN_STATES, ClaimRelationEnum
from irminsul.git.changes import working_tree_changed_paths
from irminsul.ranked_tests import Ranker
from irminsul.regen.agents_md import manifest_rel_path

if TYPE_CHECKING:
    from irminsul.change.report import ChangeBaseline, ResolvedBase

#: `path` packages what to read before editing named files and `topic` finds the docs for a
#: concept; neither runs a check. `after-edit` maps the change made and is the one mode
#: that does.
ContextMode = Literal["path", "topic", "after-edit"]
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
DEFAULT_PACKET_CONTENT: tuple[ContentCategory, ...] = (
    "owner",
    "boundary",
    "claims",
    "requirements",
)
#: The one section excerpted beyond the doc's opening block. A component doc states what
#: it does in its first paragraph and what it deliberately does *not* do here, and the
#: second is what an agent about to add behaviour needs — `docgraph.md` says it does not
#: parse source or infer semantics only under this heading, so a packet without it would
#: show nothing about the boundary being crossed.
_BOUNDARY_HEADING = "scope & limitations"
_CLAIM_REF_RE = re.compile(r"claim:([A-Za-z0-9_.-]+)")
_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")
_MAX_CONTENT_EXCERPTS = 8
#: How many active RFCs a packet names before it starts counting instead.
#: The list is the one part of the packet that grows with the repository rather than
#: with the change. Naming a few and counting the rest keeps the packet readable and,
#: unlike printing all of them, is honest about being a selection. Claim reviews are
#: deliberately *not* capped — they are the obligations a reader must answer, not
#: supporting material.
_MAX_ACTIVE_CHANGES = 8
_MAX_EXCERPT_LINES = 20
_MAX_EXCERPT_CHARS = 1_200
#: How many tests plain output lists when none has a reason to be named. A test with a
#: reason is always listed; the JSON carries every test either way.
_MAX_UNREASONED_TESTS = 10


class ContextError(UserError):
    """User-facing context command error."""


@dataclass(frozen=True)
class DocRef:
    id: str
    title: str
    path: str
    status: str


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

    `omitted_ids` names them, because a count is not retrievable. `irminsul list lifecycle`
    lists lifecycle findings and the accepted backlog, so an omitted *draft* — half of what
    is eligible here — appears in neither. An id costs a few bytes, which is what the bound
    is spending, and it is what `retrieve` (`irminsul change status <rfc-id>`, see
    `_bound_active_changes`) takes.
    """

    shown: list[ActiveChange]
    omitted: int = 0
    omitted_ids: list[str] = field(default_factory=list)
    retrieve: str | None = None


@dataclass(frozen=True)
class RepositoryValidation:
    """What the checks said about the whole tree, after the baseline — the verdict plain
    `irminsul check` reaches. `baseline` is the run's baseline report, the same object
    `check --format json` carries, so what the baseline hid is never left out."""

    state: Literal["passed", "failed"]
    errors: int
    warnings: int
    baseline: dict[str, object] = field(default_factory=dict)


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
    #: What a `passed` or `failed` verdict leaves out, when it leaves something out: with no
    #: base the checks that judge a change did not run, so a zero says nothing about them.
    note: str | None = None


@dataclass(frozen=True)
class EditValidation:
    """The two verdicts `--after-edit` reaches, which answer different questions.

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
    """The excerpts a result carries, in category order, and what the bound left out.

    `omitted` counts, per category, the eligible excerpts the bound dropped, so a caller
    can tell a complete packet from a clipped one.
    """

    included: list[ContentExcerpt]
    omitted: dict[str, int]


@dataclass(frozen=True)
class ContextResult:
    """One owning doc and what an agent needs from it for the paths in hand.

    A field that does not apply to the mode is absent from the JSON, never `[]`:
    `findings` and `hints` appear only after an edit, the one mode that runs the checks,
    because an empty list would read as a clean result nobody looked for. `active_changes`
    appears outside topic mode, and `content` when excerpts were asked for, which a topic
    lookup does only under `--include`.
    """

    input: list[str]
    owner: DocRef
    source_claims: list[str]
    entrypoint: str | None
    tests: list[str]
    depends_on: list[DocRef]
    depends_on_missing: list[str]
    depended_on_by: list[DocRef]
    #: `None` outside `after-edit`, which alone runs the checks; it is never reported as an
    #: empty list, because having not looked is not having found nothing.
    findings: list[Finding] | None
    hints: list[str]
    active_changes: ActiveChanges = field(default_factory=lambda: ActiveChanges(shown=[]))
    content: ContextContent | None = None
    #: `findings` as `check --format json` reports them, each with its `irminsul fix`
    #: command when one remediates it; `None` exactly when `findings` is.
    records: list[dict[str, object]] | None = None
    #: Why each test in `tests` is named, for the ones that have a reason; `tests` is in
    #: ranked order, and a test absent here is listed for nothing but being owned.
    test_reasons: dict[str, list[str]] = field(default_factory=dict)
    #: The inputs that do not exist yet. They are owned by the doc whose `describes:` glob
    #: would cover them, which is what a path packet is asked for before a file is created.
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GoverningClaim:
    """A claim whose evidence names a path, and the doc that declares it."""

    doc: DocRef
    claim_id: str
    relation: str
    claim: str


@dataclass(frozen=True)
class UnmatchedPath:
    """A path no doc owns. `recorded_debt` is set when the adoption record excepts it, and
    says what editing it costs: `diff-integrity` fails a change that edits such a file
    without giving it an owner, which an agent otherwise learns at the last step."""

    path: str
    reason: str
    candidates: list[DocRef]
    governed_by: list[GoverningClaim] = field(default_factory=list)
    recorded_debt: str | None = None
    #: The path is not on disk yet.
    missing: bool = False


@dataclass(frozen=True)
class ClaimReview:
    """A `governs-evidence` or `review-on-divergence` claim whose evidence the paths include.

    A request to a reader, not a finding: nothing here says the claim is broken, and
    nothing mechanical could. What it says is that the change reached the code a
    claim is written against, so somebody has to decide whether the claim still
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
    """What one `irminsul context` call reports, in the shape `--format json` prints.

    `results` has one entry per owning doc and `unmatched` the paths no doc owns.
    `claim_reviews` lists the claims whose evidence the paths in hand cite, so a topic
    lookup, which has no paths, has none. `validation` is set only after an edit: a mode
    that ran no checks leaves it out of the JSON rather than reporting an empty verdict.
    `next_actions` are command-and-reason pairs derived from the report's own state; a
    topic report carries `suggestion` in their place, null when a doc matched and otherwise
    the sentence the plain output prints after `(none)`.
    """

    version: int
    mode: ContextMode
    results: list[ContextResult]
    unmatched: list[UnmatchedPath]
    validation: EditValidation | None = None
    next_actions: list[NextAction] = field(default_factory=list)
    claim_reviews: list[ClaimReview] = field(default_factory=list)
    suggestion: str | None = None


@dataclass(frozen=True)
class _Ownership:
    node: DocNode | None
    pattern: str | None
    candidates: tuple[DocNode, ...]
    reason: str | None


@dataclass(frozen=True)
class _PendingResult:
    node: DocNode
    inputs: tuple[str, ...]
    source_claims: tuple[str, ...]
    #: The inputs that are not on disk yet, owned by the glob that would cover them.
    missing: tuple[str, ...] = ()


@dataclass
class _ChangedGroup:
    node: DocNode
    inputs: set[str]
    source_claims: set[str]
    missing: set[str] = field(default_factory=set)


def build_context_report(
    repo_root: Path,
    config: IrminsulConfig,
    *,
    target_paths: Iterable[Path] | None = None,
    topic: str | None = None,
    after_edit: bool = False,
    content_categories: Iterable[ContentCategory] | None = None,
    base_ref: str | None = None,
    committed_only: bool = False,
) -> ContextReport:
    """Build task-specific navigation context from the current doc graph.

    Only `after_edit` runs the checks. A packet for files not yet edited is a retrieval
    step: a check pass over the whole tree says nothing about them, and it would be nearly
    all of the cost of every call.

    When a base resolves, the change runs from its merge base with `HEAD` to the working
    tree, or to `HEAD` under `committed_only`. The graph carries that range, so the passes
    `check --diff` adds run here too, and the paths it changed are the ones reported on.
    """
    paths = tuple(target_paths) if target_paths is not None else None
    if sum([paths is not None, topic is not None, after_edit]) != 1:
        raise ContextError(
            "choose exactly one input mode: <path...>, --topic <query>, or --after-edit"
        )
    if base_ref is not None and not after_edit:
        raise ContextError("--base-ref applies to --after-edit only")

    mode: ContextMode = (
        "path" if paths is not None else "topic" if topic is not None else "after-edit"
    )
    if content_categories is None:
        categories = () if mode == "topic" else DEFAULT_PACKET_CONTENT
    else:
        categories = _normalize_content_categories(content_categories)
    include_content = mode != "topic" or content_categories is not None

    base = _resolve_base(repo_root, base_ref, committed_only) if after_edit else None
    graph = build_graph(
        repo_root,
        config,
        change=_change_range(base, committed_only),
        committed_only=committed_only,
    )

    if paths is not None:
        pending, unmatched = _pending_for_paths(repo_root, graph, paths)
    elif topic is not None:
        pending = _pending_for_topic(graph, topic)
        unmatched = []
    else:
        assert base is not None
        changed = base.baseline.changed_paths
        if changed is None:
            changed = (
                () if committed_only else tuple(working_tree_changed_paths(graph.git, repo_root))
            )
        pending, unmatched = _pending_for_changed(graph, list(changed))

    # Topic mode's inputs are query terms, not paths, so it has no subject files.
    subjects: set[str] = set()
    if mode != "topic":
        subjects = {path for item in pending for path in item.inputs}
        subjects.update(item.path for item in unmatched)
    claim_reviews = claim_reviews_for_paths(graph, subjects, after_change=mode == "after-edit")
    reviewed_by_doc: dict[str, set[str]] = {}
    for review in claim_reviews:
        reviewed_by_doc.setdefault(review.doc.path, set()).add(review.claim_id)

    run = _run_checks(graph) if mode == "after-edit" else None
    ranker = Ranker(graph) if mode != "topic" else None
    results = [
        _build_result(
            graph,
            item,
            run.findings if run is not None else None,
            ranker=ranker,
            include_active_changes=mode != "topic",
            content_categories=categories if include_content else None,
            reviewed_claims=frozenset(reviewed_by_doc.get(item.node.path.as_posix(), ())),
        )
        for item in pending
    ]
    validation = (
        _edit_validation(graph, run, base.baseline)
        if run is not None and base is not None
        else None
    )
    next_actions = (
        _next_actions(
            mode,
            results,
            unmatched,
            validation,
            has_unowned_source=_has_unowned_source(repo_root, config, unmatched),
            claim_reviews=claim_reviews,
        )
        if mode != "topic"
        else []
    )
    return ContextReport(
        version=1,
        mode=mode,
        results=results,
        unmatched=unmatched,
        validation=validation,
        next_actions=next_actions,
        claim_reviews=claim_reviews,
        suggestion=_TOPIC_MISS_SUGGESTION if mode == "topic" and not results else None,
    )


def context_report_should_fail(report: ContextReport) -> bool:
    """Whether the CLI should return non-zero after printing a report.

    After an edit the edit-specific signal is what this change introduced, so a sound
    change comparison decides. Where none could be established the whole-repository
    verdict decides instead — the safe existing behaviour, rather than a silent success.
    A mode that ran no checks never fails on validation: it established nothing, and
    exit 0 there means the packet was produced, not that the tree is clean. A path packet
    in which no named path has an owner does fail.
    """
    validation = report.validation
    if validation is not None:
        if validation.change.state != "not_run":
            return validation.change.state == "failed"
        return validation.repository.state == "failed"
    return report.mode == "path" and not report.results


def context_report_to_json(report: ContextReport) -> str:
    return json.dumps(_report_to_dict(report), indent=2)


def parse_content_categories(raw: str) -> tuple[ContentCategory, ...]:
    values = [value.strip().lower() for value in raw.split(",") if value.strip()]
    if not values:
        raise ContextError("--include requires one or more content categories")
    if "all" in values:
        if len(values) != 1:
            raise ContextError("--include all cannot be combined with other categories")
        return CONTENT_CATEGORY_ORDER
    if "none" in values:
        if len(values) != 1:
            raise ContextError("--include none cannot be combined with other categories")
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
            f"unknown --include categories: {', '.join(unknown)}; expected {expected}"
        )
    return tuple(category for category in CONTENT_CATEGORY_ORDER if category in selected)


def format_context_plain(report: ContextReport) -> str:
    lines: list[str] = []
    if not report.results and not report.unmatched and report.mode == "topic":
        return f"(none)\n{report.suggestion}" if report.suggestion else "(none)"

    for result in report.results:
        if lines:
            lines.append("")
        lines.extend(_format_result(result, include_active_changes=report.mode != "topic"))

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
            if item.missing:
                suffix += " (does not exist)"
            lines.append(f"  {item.path}: {item.reason}{suffix}")
            for governing in item.governed_by:
                if (governing.doc.path, governing.claim_id) in reviewed:
                    continue  # the claims-to-review block below says more about it
                lines.append(
                    f"    governed by {governing.claim_id} ({governing.relation}) "
                    f"in {governing.doc.path}"
                )
                lines.append(f"      {governing.claim}")
            if item.recorded_debt:
                lines.append(f"    {item.recorded_debt}")

    if report.claim_reviews:
        if lines:
            lines.append("")
        header = (
            "Claims to review — this change touched their evidence:"
            if report.mode == "after-edit"
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

    if report.mode != "topic":
        if lines:
            lines.append("")
        if report.validation is not None:
            lines.extend(_validation_lines(report.validation))
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
        raise ContextError("path input cannot be empty")

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
            group.missing.update(item.missing)

    pending = [
        _PendingResult(
            node=group.node,
            inputs=tuple(sorted(group.inputs)),
            source_claims=tuple(sorted(group.source_claims)),
            missing=tuple(sorted(group.missing)),
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
    rel, exists = _repo_relative(repo_root, target_path, source_roots)
    display = rel.as_posix()
    missing = () if exists else (display,)

    node = graph.by_path.get(rel)
    if node is not None:
        return [
            _PendingResult(
                node=node,
                inputs=(display,),
                source_claims=tuple(node.frontmatter.describes),
            )
        ], []

    routed = _declared_test_routes(graph, [display]).get(display, ())
    if routed:
        return [
            _PendingResult(node=owner, inputs=(display,), source_claims=(), missing=missing)
            for owner in routed
        ], []

    ownership = _ownership_for_source_path(resolve_claims(graph, [display]).get(display, []))
    if ownership.node is not None:
        return [
            _PendingResult(
                node=ownership.node,
                inputs=(display,),
                source_claims=(ownership.pattern,) if ownership.pattern else (),
                missing=missing,
            )
        ], []

    return [], [
        _unmatched(graph, display, ownership, _governing_claims(graph, display), missing=not exists)
    ]


def _unmatched(
    graph: DocGraph,
    display: str,
    ownership: _Ownership,
    governed_by: list[GoverningClaim],
    *,
    missing: bool = False,
) -> UnmatchedPath:
    return UnmatchedPath(
        path=display,
        reason=ownership.reason or "no owning doc found",
        candidates=[_doc_ref(node) for node in ownership.candidates],
        governed_by=governed_by,
        recorded_debt=None if ownership.candidates else _recorded_debt_note(graph, display),
        missing=missing,
    )


def _recorded_debt_note(graph: DocGraph, display: str) -> str | None:
    """What editing `display` costs when the adoption record excepts it, else `None`.

    Only a file the packet found no owner for is asked, and a tie has candidates: a file
    that two docs claim is owned as far as `diff-integrity` is concerned, so its entry has
    retired and nothing is owed.
    """
    debt = recorded_debt(graph)
    if debt is None or graph.config is None or display not in debt:
        return None
    return (
        f"recorded as pre-existing ownership debt in {graph.config.paths.adoption}; a change "
        "that edits it must give it an owning doc in the same change (add it to a doc's "
        "`describes:`, or `owns_tests:` for a test, or run `irminsul new component`), or "
        "`check --diff` fails with `diff-integrity/adoption-debt-touched`"
    )


def _pending_for_topic(graph: DocGraph, topic: str) -> list[_PendingResult]:
    query = topic.strip()
    if not query:
        raise ContextError("topic query cannot be empty")

    terms = tuple(query.lower().split())
    normalized_query = " ".join(terms)
    normalized_phrase = _normalize_topic_phrase(normalized_query) or normalized_query
    matches: list[_TopicMatch] = []
    for node in graph.nodes.values():
        headings = [heading.text for heading in graph.headings.get(node.id, [])]
        if (match := _match_topic(node, headings, terms, normalized_phrase)) is not None:
            matches.append(match)
    if not matches:
        return []

    matches.sort(
        key=lambda match: (
            match.needs_headings,
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
    graph: DocGraph,
    changed_paths: list[str],
) -> tuple[list[_PendingResult], list[UnmatchedPath]]:
    groups: dict[str, _ChangedGroup] = {}
    unmatched: list[UnmatchedPath] = []

    changed_claims = resolve_claims(graph, changed_paths)
    test_owners = _declared_test_routes(graph, changed_paths)
    unowned_by_design = _tool_files(graph.config) | {file.display for file in graph.guidance_files}

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

        ownership = _ownership_for_source_path(changed_claims.get(changed_path, []))
        if ownership.node is not None:
            group = groups.setdefault(
                ownership.node.id,
                _ChangedGroup(node=ownership.node, inputs=set(), source_claims=set()),
            )
            group.inputs.add(changed_path)
            if ownership.pattern:
                group.source_claims.add(ownership.pattern)
            continue

        governed_by = _governing_claims(graph, changed_path)
        if changed_path in unowned_by_design and not governed_by:
            continue
        unmatched.append(_unmatched(graph, changed_path, ownership, governed_by))

    pending = [
        _PendingResult(
            node=group.node,
            inputs=tuple(sorted(group.inputs)),
            source_claims=tuple(sorted(group.source_claims)),
        )
        for group in sorted(groups.values(), key=lambda g: g.node.path.as_posix())
    ]
    unmatched.sort(key=lambda item: item.path)
    return pending, unmatched


def _tool_files(config: IrminsulConfig | None) -> frozenset[str]:
    """The files Irminsul writes and judges itself, named by the paths the config sets.

    No doc is meant to own the baseline, the adoption record or the manifest, so editing one
    is not a gap an agent should answer by finding it an owner.
    """
    if config is None:
        return frozenset()
    names = (config.paths.baseline, config.paths.adoption, manifest_rel_path(config).as_posix())
    return frozenset(posixpath.normpath(name.replace("\\", "/")) for name in names)


def _declared_test_routes(
    graph: DocGraph, changed_paths: list[str]
) -> dict[str, tuple[DocNode, ...]]:
    """Which docs each path reaches through a declared test reference.

    Matched with the shared resolver, so a directory or glob entry routes the way it
    matches everywhere else; a raw string comparison would route `tests/` to nothing at all.
    A doc that owns a test routes to it even when its `recommended_tests:` names others,
    and a doc that only recommends a shared test still appears, because whoever edits that
    test wants the context of everyone who runs it.
    """
    assert graph.config is not None
    routes: dict[str, list[DocNode]] = {}
    for node in graph.nodes.values():
        declared = [*node.frontmatter.owns_tests, *node.frontmatter.effective_recommended_tests]
        for path in matching_paths(declared, changed_paths):
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


def _repo_relative(repo_root: Path, raw_path: Path, source_roots: list[str]) -> tuple[Path, bool]:
    """The display spelling of a path, whether the file is there, or a `ContextError`.

    A path inside the invocation root answers repo-relative. Failing that, the value is
    read as a display spelling — the one `describes:` and `claims[].evidence` speak —
    which is how a source file in a sibling code repo is named: with
    `source_roots = ["../code/src"]`, `workspace/code/src/app/main.py` is `app/main.py`.
    Without it the layout would have no spelling for its own source files: the
    `../code/...` form is outside the repo and refused, and the display form does not
    exist on disk under `repo_root`.

    The mirror also holds: an existing file under a configured external root —
    `../code/src/app/main.py`, the spelling a shell tab-completes — maps to
    its display spelling instead of being refused, the encode direction of the
    same round trip. Only a path that neither lies in the repo nor maps to a
    display the tool speaks is refused as outside the repo.

    A path that is not on disk is asked about too, because that is when an agent wants to
    know which doc a new file would belong to: it answers with the spelling the file would
    have, under the repo or under an external root, and `False` for existence.
    """
    absolute = raw_path if raw_path.is_absolute() else repo_root / raw_path
    resolved = absolute.resolve()
    if resolved.exists():
        try:
            rel = resolved.relative_to(repo_root.resolve())
        except ValueError as exc:
            display_spelling = external_display_for_path(repo_root, source_roots, resolved)
            if display_spelling is not None:
                return Path(PurePosixPath(display_spelling)), True
            raise ContextError(f"path is outside the repo: {raw_path}") from exc
        return Path(PurePosixPath(*rel.parts)), True

    display = PurePosixPath(raw_path.as_posix())
    if not raw_path.is_absolute() and resolve_display_path(repo_root, source_roots, str(display)):
        return Path(display), True
    repo_abs = repo_root.resolve()
    if resolved.is_relative_to(repo_abs):
        return Path(PurePosixPath(*resolved.relative_to(repo_abs).parts)), False
    not_yet = external_display_for_path(repo_root, source_roots, resolved, not_yet_created=True)
    if not_yet is not None:
        return Path(PurePosixPath(not_yet)), False
    raise ContextError(f"path is outside the repo: {raw_path}")


@dataclass(frozen=True)
class _TopicMatch:
    node: DocNode
    exact_phrase: bool
    fields_hit: int
    needs_headings: bool


_TOPIC_METADATA: dict[str, Callable[[DocNode], str]] = {
    "id": lambda node: node.id,
    "title": lambda node: node.frontmatter.title,
    "path": lambda node: node.path.as_posix(),
    "describes": lambda node: " ".join(node.frontmatter.describes),
    "tests": lambda node: " ".join(node.frontmatter.effective_recommended_tests),
    "tags": lambda node: " ".join(node.frontmatter.tags),
    "summary": lambda node: node.frontmatter.summary or "",
}
_TOPIC_FIELDS = (*_TOPIC_METADATA, "headings")
_TOPIC_MISS_SUGGESTION = (
    f"Searched {', '.join(_TOPIC_FIELDS[:-1])} and {_TOPIC_FIELDS[-1]}, and every term must "
    "match, so try fewer words. The words may appear only in doc bodies, so search them "
    "directly. A check name or finding code is described by `irminsul explain <name>`."
)


def _topic_haystack(node: DocNode) -> dict[str, str]:
    return {field: read(node).lower() for field, read in _TOPIC_METADATA.items()}


def _normalize_topic_phrase(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.lower()).strip()


def _match_topic(
    node: DocNode,
    headings: Iterable[str],
    terms: tuple[str, ...],
    normalized_phrase: str,
) -> _TopicMatch | None:
    """A doc matches when every term is in its metadata or its heading texts.

    Headings are the fallback: a term only a heading holds makes the match rank below
    every doc whose metadata holds all the terms, and ranking signals come from the
    metadata alone unless a heading was needed.
    """
    haystack = _topic_haystack(node)
    heading_texts = [heading.lower() for heading in headings]
    fields_hit: set[str] = set()
    needs_headings = False
    for term in terms:
        term_fields = [field for field, text in haystack.items() if term in text]
        if term_fields:
            fields_hit.update(term_fields)
        elif any(term in text for text in heading_texts):
            needs_headings = True
        else:
            return None
    searched = [*haystack.values(), *heading_texts] if needs_headings else haystack.values()
    exact_phrase = any(normalized_phrase in _normalize_topic_phrase(text) for text in searched)
    return _TopicMatch(
        node=node,
        exact_phrase=exact_phrase,
        fields_hit=len(fields_hit),
        needs_headings=needs_headings,
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
    for text, first, last in _paragraphs(node.body):
        if claim_id not in set(_CLAIM_REF_RE.findall(text)):
            continue
        for link in node.links:
            target = linked_node(node, link, graph.by_path)
            if (
                first <= link.line <= last
                and target is not None
                and in_layer(config, target.path, "decisions")
            ):
                found.setdefault(target.path.as_posix(), _doc_ref(target))
    return [found[key] for key in sorted(found)]


def _paragraphs(body: str) -> list[tuple[str, int, int]]:
    """Each blank-line-separated block of `body` with its first and last line."""
    out: list[tuple[str, int, int]] = []
    start = 0
    for separator in [*_PARAGRAPH_BREAK_RE.finditer(body), None]:
        end = len(body) if separator is None else separator.start()
        first = body.count("\n", 0, start) + 1
        out.append((body[start:end], first, first + body.count("\n", start, end)))
        if separator is not None:
            start = separator.end()
    return out


def _ownership_for_source_path(claims: list[Claim]) -> _Ownership:
    if not claims:
        return _Ownership(
            node=None,
            pattern=None,
            candidates=(),
            reason="no owning doc found",
        )

    top_claims = sorted(most_specific_claims(claims), key=lambda claim: claim[0].path.as_posix())
    if len(top_claims) > 1:
        return _Ownership(
            node=None,
            pattern=None,
            candidates=tuple(node for node, _, _ in top_claims),
            reason="ambiguous ownership",
        )

    node, pattern, _ = top_claims[0]
    return _Ownership(
        node=node,
        pattern=pattern,
        candidates=(node,),
        reason=None,
    )


def _run_checks(graph: DocGraph) -> RunResult:
    """The run plain `irminsul check` makes over this graph, baseline and all.

    `--after-edit` is the step the agent loop puts between editing and committing, and its
    verdict is what an agent acts on, so it is the shared run rather than one assembled
    here: a run assembled here would drift from it, leaving out the ignore-comment audit,
    the baseline or the passes that judge the run.
    """
    from irminsul.checks.pipeline import run_checks

    return run_checks(graph)


def _build_result(
    graph: DocGraph,
    pending: _PendingResult,
    all_findings: list[Finding] | None,
    *,
    ranker: Ranker | None = None,
    include_active_changes: bool = False,
    content_categories: tuple[ContentCategory, ...] | None = None,
    reviewed_claims: frozenset[str] = frozenset(),
) -> ContextResult:
    node = pending.node
    source_claims = list(pending.source_claims) or list(node.frontmatter.describes)
    ranking = ranker.rank(node, pending.inputs) if ranker is not None else None
    relevant_findings = (
        _relevant_findings(all_findings, node, pending.inputs) if all_findings is not None else None
    )
    records = finding_records(relevant_findings, graph) if relevant_findings is not None else None
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
        tests=ranking.tests
        if ranking is not None
        else list(node.frontmatter.effective_recommended_tests),
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
        findings=relevant_findings,
        hints=[] if records is None else _hints(records),
        active_changes=_bound_active_changes(all_changes)
        if include_active_changes
        else ActiveChanges(shown=[]),
        content=(
            _build_context_content(graph, node, all_changes, content_categories, reviewed_claims)
            if content_categories is not None
            else None
        ),
        records=records,
        test_reasons=ranking.reasons if ranking is not None else {},
        missing_inputs=list(pending.missing),
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
        if state not in RFC_OPEN_STATES:
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
    section = section_lines(
        node.body,
        headings_of(node.tokens),
        lambda heading: heading.text.lower() == _BOUNDARY_HEADING,
    )
    if section is None:
        return None
    body = re.sub(r"<!--.*?-->", "", "\n".join(section), flags=re.DOTALL).strip()
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


def _validation_lines(validation: EditValidation) -> list[str]:
    """Both verdicts, the second saying plainly whether it was reached at all."""
    repository = validation.repository
    lines = [
        f"Repository validation: {repository.state} "
        f"({repository.errors} errors, {repository.warnings} warnings)"
    ]
    baseline = repository.baseline
    if baseline.get("applied"):
        stale = baseline.get("stale")
        stale_note = (
            f"; {stale} fixed entr{'y' if stale == 1 else 'ies'} for irminsul baseline update"
            if isinstance(stale, int) and stale > 0
            else ""
        )
        lines.append(
            f"  baseline: {baseline.get('suppressed')} certain finding(s) hidden by "
            f"{baseline.get('path')}{stale_note}; irminsul list baseline shows them"
        )
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
        if change.note:
            lines.append(f"  note: {change.note}")
    return lines


def _resolve_base(repo_root: Path, base_ref: str | None, committed_only: bool) -> ResolvedBase:
    """Where the change starts, as `resolve_base` answers it."""
    from irminsul.change.report import resolve_base
    from irminsul.git.reader import GitReader

    return resolve_base(GitReader(), repo_root, base_ref, committed_only=committed_only)


def _change_range(base: ResolvedBase | None, committed_only: bool) -> ChangeRange | None:
    """The range the diff passes judge, for a base that names one.

    `HEAD` as the default base gives none: with nothing to compare against, the passes that
    judge a change have no change to judge, and the comparison with `HEAD` is the delta's.
    """
    if base is None or base.since is None or base.baseline.ref is None:
        return None
    return range_of(base.baseline.ref, base.since, committed_only=committed_only)


def _edit_validation(graph: DocGraph, run: RunResult, baseline: ChangeBaseline) -> EditValidation:
    warnings = sum(finding.severity.value == "warning" for finding in run.findings)
    return EditValidation(
        repository=RepositoryValidation(
            state="failed" if run.failed() else "passed",
            errors=len(run.failing()),
            warnings=warnings,
            baseline=run.baseline_report(),
        ),
        change=_change_validation(graph, run, baseline),
    )


def _change_validation(
    graph: DocGraph, run: RunResult, baseline: ChangeBaseline
) -> ChangeValidation:
    """What this edit introduced, or why that could not be established.

    The comparison is `check --delta`'s own, `run_delta`, so "new" means a finding the
    same run at the base did not produce — not a finding whose file the edit happened to
    touch. Everything that can go wrong here ends as `not_run` with a reason, because the
    one answer this must never give is a zero it did not measure.
    """
    from irminsul.change.report import BaselineSource
    from irminsul.checks.pipeline import failing_findings, run_delta
    from irminsul.delta import DeltaError

    if baseline.source == BaselineSource.committed:
        return ChangeValidation(
            state="not_run",
            baseline=None,
            reason=(
                "--committed-only without a base ends the change where it starts, so no change "
                "is judged and nothing uncommitted is read; pass --base-ref <ref> to judge a "
                "branch's commits"
            ),
        )
    if baseline.changed_paths is None:
        return ChangeValidation(
            state="not_run",
            baseline=baseline.ref,
            reason=(
                f"base ref {baseline.ref!r} could not be resolved; pass --base-ref <ref> "
                "naming a ref this repository has"
                if baseline.ref is not None
                else "no diff baseline could be resolved; pass --base-ref <ref> or set "
                "IRMINSUL_BASE_REF"
            ),
        )
    rev = baseline.ref or "HEAD"
    try:
        delta = run_delta(run, graph, rev, remedy="pass --base-ref <ref> naming the branch point")
    except DeltaError as exc:
        # With no base, `rev` is HEAD, which already holds whatever this branch committed:
        # every finding would count as pre-existing and the answer would be a zero that
        # measured nothing.
        return ChangeValidation(state="not_run", baseline=rev, reason=str(exc))

    new_errors = len(failing_findings(delta.new))
    return ChangeValidation(
        state="passed" if new_errors == 0 else "failed",
        new_errors=new_errors,
        baseline=rev,
        note=_unjudged_note() if graph.change is None else None,
    )


def _unjudged_note() -> str:
    """Why a verdict reached with no change range says nothing about the passes that judge one.

    With no base the working tree is compared with `HEAD` by the delta alone. `check --diff HEAD`
    is the same uncommitted work with those passes run, so it is the command to name.
    """
    names = ", ".join(f"`{name}`" for name in CHANGE_PASSES)
    return (
        f"no base was given, so the working tree was compared with HEAD and {names}, which "
        "judge a change, did not run; `--base-ref <base>` runs them for the whole branch, "
        "`--base-ref HEAD` for the uncommitted work alone"
    )


def _next_actions(
    mode: ContextMode,
    results: list[ContextResult],
    unmatched: list[UnmatchedPath],
    validation: EditValidation | None,
    *,
    has_unowned_source: bool,
    claim_reviews: list[ClaimReview],
) -> list[NextAction]:
    actions: list[NextAction] = []

    for review in claim_reviews:
        touched = (
            "This change touched evidence" if mode == "after-edit" else "These paths are evidence"
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

    if validation is not None:
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

    if mode == "path":
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
    return any(
        is_configured_source_path(repo_root, config, item.path)
        for item in unmatched
        if not item.missing
    )


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


def _hints(records: list[dict[str, object]]) -> list[str]:
    """Next commands for this result: remediations first, then the gate.

    Remediations come from the same finding-to-fix mapping the findings surfaces
    use, so a hint is only offered when the check actually harvests a fix for
    that finding. The verification gate stays last because it is the terminal
    step regardless of what precedes it.
    """
    hints = [str(record["fix_command"]) for record in records if "fix_command" in record]
    hints.append("irminsul check")
    return _unique(hints)


def _doc_ref(node: DocNode) -> DocRef:
    return DocRef(
        id=node.id,
        title=node.frontmatter.title,
        path=node.path.as_posix(),
        status=node.frontmatter.status.value,
    )


def _report_to_dict(report: ContextReport) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": report.version,
        "mode": report.mode,
        "results": [
            _result_to_dict(result, include_active_changes=report.mode != "topic")
            for result in report.results
        ],
        "unmatched": [_unmatched_to_dict(item) for item in report.unmatched],
        "claim_reviews": [_claim_review_to_dict(review) for review in report.claim_reviews],
    }
    if report.validation is not None:
        payload["validation"] = _validation_to_dict(report.validation)
    if report.mode != "topic":
        payload["next_actions"] = [_next_action_to_dict(action) for action in report.next_actions]
    else:
        payload["suggestion"] = report.suggestion
    return payload


def _result_to_dict(
    result: ContextResult,
    *,
    include_active_changes: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "input": result.input,
        "owner": _doc_ref_to_dict(result.owner),
        "source_claims": result.source_claims,
        "entrypoint": result.entrypoint,
        "tests": result.tests,
        "test_reasons": result.test_reasons,
        "missing_inputs": result.missing_inputs,
        "depends_on": [_doc_ref_to_dict(doc) for doc in result.depends_on],
        "depends_on_missing": result.depends_on_missing,
        "depended_on_by": [_doc_ref_to_dict(doc) for doc in result.depended_on_by],
    }
    if result.records is not None:
        payload["findings"] = result.records
        payload["hints"] = result.hints
    if include_active_changes:
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


def _validation_to_dict(validation: EditValidation) -> dict[str, object]:
    repository = validation.repository
    change = validation.change
    payload: dict[str, object] = {
        "repository": {
            "state": repository.state,
            "errors": repository.errors,
            "warnings": repository.warnings,
            "baseline": repository.baseline,
        },
        "change": {
            "state": change.state,
            "new_errors": change.new_errors,
            "baseline": change.baseline,
            "reason": change.reason,
            "note": change.note,
        },
    }
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
        "recorded_debt": item.recorded_debt,
        "missing": item.missing,
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


def _format_result(result: ContextResult, *, include_active_changes: bool = False) -> list[str]:
    lines = [
        f"owner: {result.owner.id} ({result.owner.path})",
        f"  title: {result.owner.title}",
        f"  input: {_format_list(_input_labels(result))}",
        f"  source claims: {_format_list(result.source_claims)}",
        f"  entrypoint: {result.entrypoint or '-'}",
        *_format_tests(result),
        f"  depends_on: {_format_doc_refs(result.depends_on, result.depends_on_missing)}",
        f"  depended-on-by: {_format_doc_refs(result.depended_on_by, [])}",
    ]
    if include_active_changes:
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
    if result.findings is None:
        return lines
    if result.findings:
        lines.append("  findings:")
        for finding in result.findings:
            location = finding.path.as_posix() if finding.path else "<repo>"
            if finding.line is not None:
                location = f"{location}:{finding.line}"
            # Same identity convention as `irminsul check`: the bracketed code
            # is what `irminsul explain <code>` accepts; severity stays visible.
            lines.append(
                f"    {finding.severity.value}  [{finding.code}] {location}: {finding.message}"
            )
            if finding.suggestion:
                lines.append(f"      suggestion: {finding.suggestion}")
    else:
        lines.append("  findings: (none)")
    lines.append(f"  hints: {_format_list(result.hints)}")
    return lines


def _input_labels(result: ContextResult) -> list[str]:
    return [
        f"{path} (does not exist)" if path in result.missing_inputs else path
        for path in result.input
    ]


def _format_tests(result: ContextResult) -> list[str]:
    """The tests line, or a list when some test has a reason or there are too many to run on.

    Every test with a reason is listed with it. When none has one, the first few are, so a
    doc that owns forty tests does not print forty paths for a file none of them was
    chosen for. What is left out is counted, and the JSON lists all of it.
    """
    tests = result.tests
    reasons = result.test_reasons
    if not reasons and len(tests) <= _MAX_UNREASONED_TESTS:
        return [f"  tests: {_format_list(tests)}"]
    shown = [test for test in tests if test in reasons] or tests[:_MAX_UNREASONED_TESTS]
    lines = ["  tests:"]
    for test in shown:
        why = reasons.get(test)
        lines.append(f"    {test}: {'; '.join(why)}" if why else f"    {test}")
    if left := len(tests) - len(shown):
        lines.append(
            f"    … {left} more owned by {result.owner.path} (--format json lists every test)"
        )
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
