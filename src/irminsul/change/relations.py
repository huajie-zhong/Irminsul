"""Lifecycle-aware RFC dependency and supersession graph (RFC 0042)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from irminsul.change.report import ChangeError
from irminsul.config import IrminsulConfig, docs_root_prefix
from irminsul.docgraph import DocGraph, DocNode, build_graph
from irminsul.frontmatter import RfcStateEnum, canonical_rfc_state

RELATION_GRAPH_VERSION = 1
RelationFilter = Literal["all", "dependency", "supersession"]
RelationKind = Literal["dependency", "supersession"]


@dataclass(frozen=True)
class RelationNode:
    id: str
    path: str
    title: str
    state: str | None
    status: str


@dataclass(frozen=True)
class RelationEdge:
    relation: RelationKind
    source: str
    target: str
    status: str
    path: str
    line: int | None


@dataclass(frozen=True)
class RelationCycle:
    relation: RelationKind
    members: tuple[str, ...]


@dataclass(frozen=True)
class RelationIssue:
    code: str
    relation: RelationKind
    source: str | None
    target: str | None
    members: tuple[str, ...]
    path: str | None
    line: int | None
    message: str


@dataclass(frozen=True)
class RelationGraph:
    version: int
    relation: RelationFilter
    focus: str | None
    nodes: tuple[RelationNode, ...]
    edges: tuple[RelationEdge, ...]
    cycles: tuple[RelationCycle, ...]
    issues: tuple[RelationIssue, ...]


def build_relation_graph(
    repo_root: Path,
    config: IrminsulConfig,
    *,
    focus: str | None = None,
    relation: RelationFilter = "all",
    graph: DocGraph | None = None,
) -> RelationGraph:
    if relation not in ("all", "dependency", "supersession"):
        raise ChangeError(
            f"unknown relation '{relation}'; expected all, dependency, or supersession",
            code=2,
        )
    if graph is None:
        graph = build_graph(repo_root, config)

    rfc_nodes = {node.id: node for node in graph.nodes.values() if _is_rfc(node, config)}
    focus_id = _resolve_focus(graph, config, rfc_nodes, focus) if focus else None
    selected_relations = _selected_relations(relation)

    edges: list[RelationEdge] = []
    issues: list[RelationIssue] = []
    for node in sorted(rfc_nodes.values(), key=lambda item: item.id):
        if "dependency" in selected_relations:
            _add_dependency_edges(graph, node, rfc_nodes, edges, issues)
        if "supersession" in selected_relations:
            _add_supersession_edges(graph, node, rfc_nodes, edges, issues)

    cycles: list[RelationCycle] = []
    for relation_kind in selected_relations:
        for members in _cycle_components(rfc_nodes, edges, relation_kind):
            cycle = RelationCycle(relation=relation_kind, members=members)
            cycles.append(cycle)
            issues.append(
                RelationIssue(
                    code=f"{relation_kind}-cycle",
                    relation=relation_kind,
                    source=None,
                    target=None,
                    members=members,
                    path=None,
                    line=None,
                    message=(f"{relation_kind} cycle contains: {', '.join(members)}"),
                )
            )

    if "supersession" in selected_relations:
        _add_successor_conflicts(edges, issues)

    included_ids = set(rfc_nodes)
    if focus_id is not None:
        included_ids = _connected_component(focus_id, edges, rfc_nodes)
        edges = [edge for edge in edges if edge.source in included_ids]
        cycles = [cycle for cycle in cycles if set(cycle.members) <= included_ids]
        issues = [issue for issue in issues if _issue_in_scope(issue, included_ids)]

    nodes = tuple(_relation_node(rfc_nodes[node_id]) for node_id in sorted(included_ids))
    return RelationGraph(
        version=RELATION_GRAPH_VERSION,
        relation=relation,
        focus=focus_id,
        nodes=nodes,
        edges=tuple(sorted(edges, key=_edge_sort_key)),
        cycles=tuple(sorted(cycles, key=lambda item: (item.relation, item.members))),
        issues=tuple(sorted(issues, key=_issue_sort_key)),
    )


def _is_rfc(node: DocNode, config: IrminsulConfig) -> bool:
    prefix = f"{docs_root_prefix(config)}/80-evolution/rfcs/"
    return node.path.as_posix().startswith(prefix) and node.path.name != "INDEX.md"


def _resolve_focus(
    graph: DocGraph,
    config: IrminsulConfig,
    rfc_nodes: dict[str, DocNode],
    focus: str,
) -> str:
    node = graph.nodes.get(focus)
    if node is None:
        node = graph.by_path.get(Path(focus.replace("\\", "/")))
    if node is None and focus.isdigit():
        prefix = f"{focus.zfill(4)}-"
        matches = sorted(
            (node for node in rfc_nodes.values() if node.id.startswith(prefix)),
            key=lambda item: item.id,
        )
        if len(matches) > 1:
            ids = ", ".join(node.id for node in matches)
            raise ChangeError(f"'{focus}' is ambiguous; matches: {ids}", code=2)
        node = matches[0] if matches else None

    if node is None:
        raise ChangeError(f"no RFC found for '{focus}'", code=2)
    if not _is_rfc(node, config):
        raise ChangeError(f"'{focus}' resolves to {node.path.as_posix()}, not an RFC", code=2)
    return node.id


def _selected_relations(relation: RelationFilter) -> tuple[RelationKind, ...]:
    if relation == "all":
        return ("dependency", "supersession")
    return (relation,)


def _relation_node(node: DocNode) -> RelationNode:
    return RelationNode(
        id=node.id,
        path=node.path.as_posix(),
        title=node.frontmatter.title,
        state=_state(node),
        status=node.frontmatter.status.value,
    )


def _state(node: DocNode) -> str | None:
    state = node.frontmatter.rfc_state
    return canonical_rfc_state(state).value if state is not None else None


def _add_dependency_edges(
    graph: DocGraph,
    source: DocNode,
    rfc_nodes: dict[str, DocNode],
    edges: list[RelationEdge],
    issues: list[RelationIssue],
) -> None:
    source_state = _state(source)
    for target_id in source.frontmatter.depends_on:
        target_doc = graph.nodes.get(target_id)
        if target_doc is not None and target_id not in rfc_nodes:
            continue
        target = rfc_nodes.get(target_id)
        line = _frontmatter_item_line(graph, source, "depends_on", target_id)
        status = _dependency_status(source_state, _state(target) if target else None, target)
        if target_id == source.id:
            status = "invalid"
            issues.append(
                _edge_issue(
                    "self-reference",
                    "dependency",
                    source,
                    target_id,
                    line,
                    f"RFC '{source.id}' depends on itself",
                )
            )
        elif target is None:
            issues.append(
                _edge_issue(
                    "unknown-target",
                    "dependency",
                    source,
                    target_id,
                    line,
                    f"dependency from '{source.id}' references unknown id '{target_id}'",
                )
            )
        edges.append(
            RelationEdge(
                relation="dependency",
                source=source.id,
                target=target_id,
                status=status,
                path=source.path.as_posix(),
                line=line,
            )
        )
        if (
            source_state == RfcStateEnum.implemented.value
            and target_id != source.id
            and (target is None or _state(target) != RfcStateEnum.implemented.value)
        ):
            issues.append(
                _edge_issue(
                    "implemented-before-dependency",
                    "dependency",
                    source,
                    target_id,
                    line,
                    (
                        f"implemented RFC '{source.id}' depends on '{target_id}', "
                        "which is not implemented"
                    ),
                )
            )


def _dependency_status(
    source_state: str | None,
    target_state: str | None,
    target: DocNode | None,
) -> str:
    if target is None:
        return "invalid"
    if source_state == RfcStateEnum.rejected.value:
        return "void"
    if target_state == RfcStateEnum.implemented.value:
        return "satisfied"
    if target_state == RfcStateEnum.rejected.value:
        return "blocked"
    if target_state is None:
        return "unknown"
    return "pending"


def _add_supersession_edges(
    graph: DocGraph,
    source: DocNode,
    rfc_nodes: dict[str, DocNode],
    edges: list[RelationEdge],
    issues: list[RelationIssue],
) -> None:
    source_state = _state(source)
    for target_id in source.frontmatter.supersedes:
        target_doc = graph.nodes.get(target_id)
        if target_doc is not None and target_id not in rfc_nodes:
            continue
        target = rfc_nodes.get(target_id)
        line = _frontmatter_item_line(graph, source, "supersedes", target_id)
        status = _supersession_status(source_state, target)
        if target_id == source.id:
            status = "invalid"
            issues.append(
                _edge_issue(
                    "self-reference",
                    "supersession",
                    source,
                    target_id,
                    line,
                    f"RFC '{source.id}' supersedes itself",
                )
            )
        elif target is None:
            issues.append(
                _edge_issue(
                    "unknown-target",
                    "supersession",
                    source,
                    target_id,
                    line,
                    f"supersession from '{source.id}' references unknown id '{target_id}'",
                )
            )
        edges.append(
            RelationEdge(
                relation="supersession",
                source=source.id,
                target=target_id,
                status=status,
                path=source.path.as_posix(),
                line=line,
            )
        )

    reverse = source.frontmatter.superseded_by
    if reverse is not None:
        line = _frontmatter_item_line(graph, source, "superseded_by", reverse)
        issues.append(
            _edge_issue(
                "reverse-supersession-declaration",
                "supersession",
                source,
                reverse,
                line,
                (
                    f"RFC '{source.id}' declares superseded_by; declare supersedes "
                    "on the successor and derive the reverse edge instead"
                ),
            )
        )


def _supersession_status(source_state: str | None, target: DocNode | None) -> str:
    if target is None:
        return "invalid"
    if source_state == RfcStateEnum.implemented.value:
        return "effective"
    if source_state == RfcStateEnum.rejected.value:
        return "void"
    if source_state is None:
        return "unknown"
    return "planned"


def _edge_issue(
    code: str,
    relation: RelationKind,
    source: DocNode,
    target: str,
    line: int | None,
    message: str,
) -> RelationIssue:
    return RelationIssue(
        code=code,
        relation=relation,
        source=source.id,
        target=target,
        members=(),
        path=source.path.as_posix(),
        line=line,
        message=message,
    )


def _add_successor_conflicts(edges: list[RelationEdge], issues: list[RelationIssue]) -> None:
    by_target: dict[str, list[RelationEdge]] = {}
    for edge in edges:
        if edge.relation == "supersession" and edge.status == "effective":
            by_target.setdefault(edge.target, []).append(edge)
    for target, target_edges in sorted(by_target.items()):
        sources = tuple(sorted({edge.source for edge in target_edges}))
        if len(sources) < 2:
            continue
        issues.append(
            RelationIssue(
                code="multiple-effective-successors",
                relation="supersession",
                source=None,
                target=target,
                members=sources,
                path=None,
                line=None,
                message=(f"RFC '{target}' has multiple effective successors: {', '.join(sources)}"),
            )
        )


def _cycle_components(
    nodes: dict[str, DocNode],
    edges: list[RelationEdge],
    relation: RelationKind,
) -> tuple[tuple[str, ...], ...]:
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in edges:
        if edge.relation == relation and edge.target in nodes:
            adjacency[edge.source].add(edge.target)

    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)

        for target_id in sorted(adjacency[node_id]):
            if target_id not in indices:
                visit(target_id)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[target_id])
            elif target_id in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indices[target_id])

        if lowlinks[node_id] != indices[node_id]:
            return
        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node_id:
                break
        members = tuple(sorted(component))
        if len(members) > 1 or node_id in adjacency[node_id]:
            components.append(members)

    for node_id in sorted(nodes):
        if node_id not in indices:
            visit(node_id)
    return tuple(sorted(components))


def _connected_component(
    focus: str,
    edges: list[RelationEdge],
    nodes: dict[str, DocNode],
) -> set[str]:
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in edges:
        if edge.target not in nodes:
            continue
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    seen = {focus}
    pending = [focus]
    while pending:
        node_id = pending.pop()
        for neighbor in sorted(adjacency[node_id]):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            pending.append(neighbor)
    return seen


def _issue_in_scope(issue: RelationIssue, included_ids: set[str]) -> bool:
    if issue.source in included_ids or issue.target in included_ids:
        return True
    return bool(set(issue.members) & included_ids)


def _frontmatter_item_line(
    graph: DocGraph,
    node: DocNode,
    field: str,
    value: str,
) -> int | None:
    if graph.repo_root is None:
        return None
    try:
        lines = (graph.repo_root / node.path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    in_list = False
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped == "---" and index > 1:
            break
        if ":" in stripped and stripped.split(":", 1)[0] == field:
            in_list = True
            if _mentions(stripped.split(":", 1)[1], value):
                return index
            continue
        if not in_list:
            continue
        if stripped.startswith("- ") and _mentions(stripped[2:], value):
            return index
        if stripped and not line.startswith((" ", "\t", "-")):
            in_list = False
    return None


def _mentions(text: str, value: str) -> bool:
    cleaned = text.strip().strip("'\"")
    if cleaned == value:
        return True
    return value in re.split(r"[^A-Za-z0-9_-]+", text)


def _edge_sort_key(edge: RelationEdge) -> tuple[str, str, str, int]:
    return (edge.relation, edge.source, edge.target, edge.line or 0)


def _issue_sort_key(
    issue: RelationIssue,
) -> tuple[str, str, str, str, tuple[str, ...], str, int]:
    return (
        issue.relation,
        issue.code,
        issue.source or "",
        issue.target or "",
        issue.members,
        issue.path or "",
        issue.line or 0,
    )


def relation_graph_to_json(report: RelationGraph) -> str:
    payload = {
        "version": report.version,
        "relation": report.relation,
        "focus": report.focus,
        "nodes": [
            {
                "id": node.id,
                "path": node.path,
                "title": node.title,
                "state": node.state,
                "status": node.status,
            }
            for node in report.nodes
        ],
        "edges": [
            {
                "relation": edge.relation,
                "source": edge.source,
                "target": edge.target,
                "status": edge.status,
                "path": edge.path,
                "line": edge.line,
            }
            for edge in report.edges
        ],
        "cycles": [
            {"relation": cycle.relation, "members": list(cycle.members)} for cycle in report.cycles
        ],
        "issues": [
            {
                "code": issue.code,
                "relation": issue.relation,
                "source": issue.source,
                "target": issue.target,
                "members": list(issue.members),
                "path": issue.path,
                "line": issue.line,
                "message": issue.message,
            }
            for issue in report.issues
        ],
    }
    return json.dumps(payload, indent=2)


def format_relation_graph_plain(report: RelationGraph) -> str:
    lines = [
        f"RFC relation graph ({report.relation})",
        f"focus: {report.focus or '(repository)'}",
        "nodes:",
    ]
    if not report.nodes:
        lines.append("  (none)")
    for node in report.nodes:
        state = node.state if node.state is not None else "unclassified"
        lines.append(f"  {node.id} [{state}] {node.title} ({node.path})")

    for relation, heading in (
        ("dependency", "dependencies"),
        ("supersession", "supersessions"),
    ):
        lines.append(f"{heading}:")
        if report.relation not in ("all", relation):
            lines.append("  (not selected)")
            continue
        matching = [edge for edge in report.edges if edge.relation == relation]
        if not matching:
            lines.append("  (none)")
        for edge in matching:
            lines.append(f"  {edge.source} -> {edge.target} [{edge.status}]")

    lines.append("cycles:")
    if not report.cycles:
        lines.append("  (none)")
    for cycle in report.cycles:
        lines.append(f"  {cycle.relation}: {', '.join(cycle.members)}")

    lines.append("issues:")
    if not report.issues:
        lines.append("  (none)")
    for issue in report.issues:
        location = ""
        if issue.path is not None:
            location = f" ({issue.path}"
            if issue.line is not None:
                location += f":{issue.line}"
            location += ")"
        lines.append(f"  [{issue.code}] {issue.message}{location}")
    return "\n".join(lines)


__all__ = [
    "RELATION_GRAPH_VERSION",
    "RelationCycle",
    "RelationEdge",
    "RelationFilter",
    "RelationGraph",
    "RelationIssue",
    "RelationNode",
    "build_relation_graph",
    "format_relation_graph_plain",
    "relation_graph_to_json",
]
