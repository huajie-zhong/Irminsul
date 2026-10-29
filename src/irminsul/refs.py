"""Backlink queries for docs: what depends on or links to a doc."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from irminsul.docgraph import DocGraph, DocNode, resolve_doc_target
from irminsul.docgraph_index import linked_path
from irminsul.errors import UserError
from irminsul.frontmatter import entry_line


class RefsError(UserError):
    """User-facing refs command error."""


@dataclass(frozen=True)
class RefHit:
    doc_id: str | None
    """None for a guidance file, which is not a doc and has no id."""
    path: str
    line: int


@dataclass(frozen=True)
class DocRefsReport:
    target: str
    strong: list[RefHit]
    weak: list[RefHit]


def build_doc_refs_report(repo_root: Path, graph: DocGraph, target: str) -> DocRefsReport:
    """What names or links to a doc, or to a guidance file, which has no frontmatter to name it.

    A doc's `target` is its id; a guidance file's is its repo-relative path.
    """
    wanted = Path(_resolve_target(repo_root, graph, target))
    node = graph.by_path.get(wanted)
    return DocRefsReport(
        target=wanted.as_posix() if node is None else node.id,
        strong=[] if node is None else _strong_refs_to(repo_root, graph, node),
        weak=_weak_refs_to(graph, wanted),
    )


def _strong_refs_to(repo_root: Path, graph: DocGraph, target: DocNode) -> list[RefHit]:
    return [
        RefHit(
            doc_id=source_id,
            path=graph.nodes[source_id].path.as_posix(),
            line=_strong_ref_line(repo_root, graph.nodes[source_id], target.id),
        )
        for source_id in sorted(graph.inbound_strong.get(target.id, set()))
        if source_id in graph.nodes
    ]


def doc_refs_report_to_json(report: DocRefsReport) -> str:
    return json.dumps(
        {
            "target": report.target,
            "strong": [_ref_hit_to_dict(hit) for hit in report.strong],
            "weak": [_ref_hit_to_dict(hit) for hit in report.weak],
        },
        indent=2,
    )


def format_doc_refs_plain(report: DocRefsReport) -> str:
    lines = [f"target: {report.target}", "strong:"]
    lines.extend(_format_ref_hits(report.strong))
    lines.append("weak:")
    lines.extend(_format_ref_hits(report.weak))
    return "\n".join(lines)


def _resolve_target(repo_root: Path, graph: DocGraph, target: str) -> str:
    wanted = resolve_doc_target(graph, target)
    if wanted is not None:
        return wanted
    if _is_outside_repo(repo_root, target):
        raise RefsError(f"path is outside the repo: {target}")
    raise RefsError(_unknown_target_message(target))


def _unknown_target_message(target: str) -> str:
    from irminsul.checks.pipeline import finding_sources

    if any(target == cls.name or target in cls.explanations for cls in finding_sources().values()):
        return (
            f"unknown doc target: {target}; it names a check or finding code, "
            f"which `irminsul explain {target}` describes"
        )
    topic = f'"{target}"' if any(char.isspace() for char in target) else target
    return (
        f"unknown doc target: {target}; "
        f"`irminsul context --topic {topic}` finds the docs that cover a topic"
    )


def _is_outside_repo(repo_root: Path, target: str) -> bool:
    raw = Path(target)
    absolute = raw if raw.is_absolute() else repo_root / raw
    try:
        absolute.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return True
    return False


def _weak_refs_to(graph: DocGraph, target: Path) -> list[RefHit]:
    """Every link in a doc or a guidance file, other than the target itself, that resolves to `target`."""
    hits = [
        RefHit(doc_id=node.id, path=node.path.as_posix(), line=node.file_line(link.line))
        for node in graph.nodes.values()
        if node.path != target
        for link in node.links
        if linked_path(node.path.as_posix(), link) == target
    ]
    hits += [
        RefHit(doc_id=None, path=guidance.display, line=link.line)
        for guidance in graph.guidance_files
        if Path(guidance.display) != target
        for link in guidance.links
        if linked_path(guidance.display, link, guidance.root) == target
    ]
    return sorted(hits, key=lambda hit: (hit.path, hit.line))


def _strong_ref_line(repo_root: Path, source: DocNode, target_id: str) -> int:
    """The frontmatter line where `source` names `target_id`; 1 when the file cannot say.

    `source` names the target in `depends_on` or `implements` by id, or else through
    `resolved_by`, whose line is the key's.
    """
    path = repo_root / source.path
    for key in ("depends_on", "implements"):
        line = entry_line(path, key, target_id)
        if line is not None:
            return line
    return entry_line(path, "resolved_by") or 1


def _format_ref_hits(hits: list[RefHit]) -> list[str]:
    if not hits:
        return ["  (none)"]
    return [
        f"  {hit.path}:{hit.line}"
        if hit.doc_id is None
        else f"  {hit.doc_id} {hit.path}:{hit.line}"
        for hit in hits
    ]


def _ref_hit_to_dict(hit: RefHit) -> dict[str, object]:
    return {"doc_id": hit.doc_id, "path": hit.path, "line": hit.line}
