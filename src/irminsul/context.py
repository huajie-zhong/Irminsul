"""Runtime context lookup for agents and contributors."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pathspec import GitIgnoreSpec

from irminsul.checks import HARD_REGISTRY, SOFT_REGISTRY, Check, Finding, sort_findings
from irminsul.checks.uniqueness import specificity
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode, build_graph

ContextMode = Literal["path", "topic", "changed"]
ContextProfile = Literal["configured", "all-available"]


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
    topic: str | None = None,
    changed: bool = False,
    profile: ContextProfile = "configured",
) -> ContextReport:
    """Build task-specific navigation context from the current doc graph."""
    selected_modes = sum(
        [
            target_path is not None,
            topic is not None,
            changed,
        ]
    )
    if selected_modes != 1:
        raise ContextError(
            "choose exactly one input mode: <path>, --topic <query>, or --changed",
            code=2,
        )

    graph = build_graph(repo_root, config)

    if target_path is not None:
        pending, unmatched = _pending_for_path(repo_root, graph, target_path)
        mode: ContextMode = "path"
    elif topic is not None:
        pending = _pending_for_topic(graph, topic)
        unmatched = []
        mode = "topic"
    else:
        pending, unmatched = _pending_for_changed(repo_root, graph)
        mode = "changed"

    findings = _run_deterministic_checks(config, graph, profile) if pending else []
    results = [_build_result(graph, item, findings) for item in pending]
    return ContextReport(version=1, mode=mode, results=results, unmatched=unmatched)


def context_report_should_fail(report: ContextReport) -> bool:
    """Whether the CLI should return non-zero after printing a report."""
    return report.mode == "path" and not report.results


def context_report_to_json(report: ContextReport) -> str:
    return json.dumps(_report_to_dict(report), indent=2)


def format_context_plain(report: ContextReport) -> str:
    lines: list[str] = []
    if not report.results and not report.unmatched:
        return "(none)"

    for index, result in enumerate(report.results):
        if index:
            lines.append("")
        lines.extend(_format_result(result))

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
        lines.append("  hint: irminsul list undocumented")

    return "\n".join(lines)


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

    ownership = _ownership_for_source_path(graph, display)
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
        raise ContextError(f"no docs matched topic: {query}", code=1)

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

    for changed_path in _git_changed_paths(repo_root):
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

        ownership = _ownership_for_source_path(graph, changed_path)
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
        )
        for group in sorted(groups.values(), key=lambda g: g.node.path.as_posix())
    ]
    unmatched.sort(key=lambda item: item.path)
    return pending, unmatched


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


def _ownership_for_source_path(graph: DocGraph, source_path: str) -> _Ownership:
    claims: list[tuple[DocNode, str, tuple[int, int, int]]] = []
    for node in graph.nodes.values():
        for pattern in node.frontmatter.describes:
            spec = GitIgnoreSpec.from_lines([pattern])
            if spec.match_file(source_path):
                claims.append((node, pattern, specificity(pattern)))

    if not claims:
        return _Ownership(
            node=None,
            pattern=None,
            candidates=(),
            reason="no owning doc found",
        )

    top_score = max(claim[2] for claim in claims)
    top_claims = sorted(
        [claim for claim in claims if claim[2] == top_score],
        key=lambda claim: claim[0].path.as_posix(),
    )
    if len(top_claims) > 1:
        return _Ownership(
            node=None,
            pattern=None,
            candidates=tuple(claim[0] for claim in top_claims),
            reason="ambiguous ownership",
        )

    node, pattern, _score = top_claims[0]
    return _Ownership(node=node, pattern=pattern, candidates=(node,), reason=None)


def _git_changed_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git status failed"
        raise ContextError(detail, code=1)

    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        raw = line[3:]
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        paths.append(Path(PurePosixPath(raw)).as_posix())
    return sorted(paths)


def _run_deterministic_checks(
    config: IrminsulConfig,
    graph: DocGraph,
    profile: ContextProfile,
) -> list[Finding]:
    if profile == "configured":
        selected: list[tuple[str, Registry]] = [
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
    )


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
        if any(f"'{path}'" in finding.message for path in input_paths):
            out.append(finding)
    return out


def _hints(node: DocNode, findings: list[Finding]) -> list[str]:
    hints = ["irminsul check --profile hard"]
    if _is_docs_surface(node) or any(_is_surface_drift_finding(finding) for finding in findings):
        hints.append("irminsul regen docs-surfaces")
    return _unique(hints)


def _is_docs_surface(node: DocNode) -> bool:
    return node.path.as_posix().startswith("docs/40-reference/")


def _is_surface_drift_finding(finding: Finding) -> bool:
    return finding.check in {
        "schema-doc-drift",
        "cli-doc-drift",
        "check-surface-drift",
    } or (finding.suggestion is not None and "irminsul regen docs-surfaces" in finding.suggestion)


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
    return {
        "version": report.version,
        "mode": report.mode,
        "results": [_result_to_dict(result) for result in report.results],
        "unmatched": [_unmatched_to_dict(item) for item in report.unmatched],
    }


def _result_to_dict(result: ContextResult) -> dict[str, object]:
    return {
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
    }


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


def _format_result(result: ContextResult) -> list[str]:
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
