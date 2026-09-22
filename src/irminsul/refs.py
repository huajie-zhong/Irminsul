"""Backlink and symbol-reference queries for docs."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from markdown_it import MarkdownIt

from irminsul.docgraph import DocGraph, DocNode


class RefsError(Exception):
    """User-facing refs command error."""

    def __init__(self, message: str, *, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RefHit:
    doc_id: str
    path: str
    line: int


@dataclass(frozen=True)
class SymbolHit:
    doc_id: str
    path: str
    line: int
    match: str


@dataclass(frozen=True)
class DocRefsReport:
    target: str
    strong: list[RefHit]
    weak: list[RefHit]


@dataclass(frozen=True)
class SymbolRefsReport:
    symbol: str
    owners: list[SymbolHit]
    references: list[SymbolHit]


def build_doc_refs_report(repo_root: Path, graph: DocGraph, target: str) -> DocRefsReport:
    node = _resolve_target(repo_root, graph, target)
    strong = [
        RefHit(
            doc_id=source_id,
            path=graph.nodes[source_id].path.as_posix(),
            line=_frontmatter_list_line(repo_root, graph.nodes[source_id], "depends_on", node.id),
        )
        for source_id in sorted(graph.inbound_strong.get(node.id, set()))
        if source_id in graph.nodes
    ]
    weak = _weak_refs_to(repo_root, graph, node.id)
    return DocRefsReport(target=node.id, strong=strong, weak=weak)


def build_symbol_refs_report(graph: DocGraph, symbol: str, repo_root: Path) -> SymbolRefsReport:
    query = symbol.strip()
    if not query:
        raise RefsError("symbol query cannot be empty", code=2)

    owners: list[SymbolHit] = []
    references: list[SymbolHit] = []
    for node in graph.nodes.values():
        for pattern in node.frontmatter.describes:
            if _symbol_matches(pattern, query):
                owners.append(_symbol_hit(repo_root, node, pattern))
        for claim in node.frontmatter.claims:
            for evidence in claim.evidence:
                if _symbol_matches(evidence, query):
                    references.append(_symbol_hit(repo_root, node, evidence))

    owners.sort(key=lambda hit: (hit.path, hit.match))
    references.sort(key=lambda hit: (hit.path, hit.match))
    return SymbolRefsReport(symbol=query, owners=owners, references=references)


def doc_refs_report_to_json(report: DocRefsReport) -> str:
    return json.dumps(
        {
            "target": report.target,
            "strong": [_ref_hit_to_dict(hit) for hit in report.strong],
            "weak": [_ref_hit_to_dict(hit) for hit in report.weak],
        },
        indent=2,
    )


def symbol_refs_report_to_json(report: SymbolRefsReport) -> str:
    return json.dumps(
        {
            "symbol": report.symbol,
            "owners": [_symbol_hit_to_dict(hit) for hit in report.owners],
            "references": [_symbol_hit_to_dict(hit) for hit in report.references],
        },
        indent=2,
    )


def format_doc_refs_plain(report: DocRefsReport) -> str:
    lines = [f"target: {report.target}", "strong:"]
    lines.extend(_format_ref_hits(report.strong))
    lines.append("weak:")
    lines.extend(_format_ref_hits(report.weak))
    return "\n".join(lines)


def format_symbol_refs_plain(report: SymbolRefsReport) -> str:
    lines = [f"symbol: {report.symbol}", "owners:"]
    lines.extend(_format_symbol_hits(report.owners))
    lines.append("references:")
    lines.extend(_format_symbol_hits(report.references))
    return "\n".join(lines)


def _resolve_target(repo_root: Path, graph: DocGraph, target: str) -> DocNode:
    if target in graph.nodes:
        return graph.nodes[target]

    rel = _repo_relative_path(repo_root, target)
    node = graph.by_path.get(rel)
    if node is not None:
        return node

    raise RefsError(f"unknown doc target: {target}", code=1)


def _repo_relative_path(repo_root: Path, target: str) -> Path:
    raw = Path(target)
    absolute = raw if raw.is_absolute() else repo_root / raw
    try:
        rel = absolute.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise RefsError(f"path is outside the repo: {target}", code=2) from exc
    return Path(PurePosixPath(*rel.parts))


def _weak_refs_to(repo_root: Path, graph: DocGraph, target_id: str) -> list[RefHit]:
    md = MarkdownIt("commonmark")
    hits: list[RefHit] = []
    for source_id in graph.inbound_weak.get(target_id, set()):
        node = graph.nodes.get(source_id)
        if node is None or node.id == target_id:
            continue
        line_offset = _body_line_offset(repo_root, node)
        for href, line in _link_hrefs_with_lines(node.body, md):
            if _resolve_link_to_doc_id(node, href, graph.by_path) == target_id:
                hits.append(
                    RefHit(doc_id=node.id, path=node.path.as_posix(), line=line + line_offset)
                )
    return sorted(hits, key=lambda hit: (hit.path, hit.line))


def _link_hrefs_with_lines(body: str, md: MarkdownIt) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for token in md.parse(body):
        if token.type != "inline" or not token.children:
            continue
        line = (token.map[0] + 1) if token.map else 1
        for child in token.children:
            if child.type != "link_open":
                continue
            href = child.attrGet("href")
            if isinstance(href, str):
                out.append((href, line))
    return out


def _resolve_link_to_doc_id(
    src_node: DocNode,
    href: str,
    by_path: dict[Path, DocNode],
) -> str | None:
    if not href or href.startswith("#"):
        return None
    if "://" in href or href.startswith(("mailto:", "tel:")):
        return None

    target = href.split("#", 1)[0]
    if not target:
        return None

    doc_parent = PurePosixPath(src_node.path.as_posix()).parent
    raw = doc_parent / target
    parts: list[str] = []
    for part in raw.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    resolved = Path(*parts)
    return by_path[resolved].id if resolved in by_path else None


def _frontmatter_list_line(repo_root: Path, node: DocNode, key: str, value: str) -> int:
    path = repo_root / node.path
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 1

    in_list = False
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped == "---" and index > 1:
            break
        if stripped.startswith(f"{key}:"):
            in_list = True
            if _line_mentions_value(stripped, value):
                return index
            continue
        if not in_list:
            continue
        if stripped.startswith("- ") and _line_mentions_value(stripped[2:].strip(), value):
            return index
        if stripped and not line.startswith((" ", "\t", "-")):
            in_list = False
    return 1


def _body_line_offset(repo_root: Path, node: DocNode) -> int:
    body_lines = node.body.splitlines()
    if not body_lines:
        return 0

    path = repo_root / node.path
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0

    in_frontmatter = lines[:1] == ["---"]
    past_frontmatter = not in_frontmatter
    first_body_line = body_lines[0]
    for index, line in enumerate(lines, start=1):
        if in_frontmatter and index > 1 and line == "---":
            past_frontmatter = True
            continue
        if past_frontmatter and line == first_body_line:
            return index - 1
    return 0


def _symbol_hit(repo_root: Path, node: DocNode, match: str) -> SymbolHit:
    return SymbolHit(
        doc_id=node.id,
        path=node.path.as_posix(),
        line=_first_text_line(repo_root, node, match),
        match=match,
    )


def _first_text_line(repo_root: Path, node: DocNode, text: str) -> int:
    path = repo_root / node.path
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 1
    for index, line in enumerate(lines, start=1):
        if text in line:
            return index
    return 1


def _line_mentions_value(line: str, value: str) -> bool:
    cleaned = line.strip().strip("'\"")
    if cleaned == value:
        return True
    return value in re.split(r"[^A-Za-z0-9_-]+", line)


def _symbol_matches(candidate: str, symbol: str) -> bool:
    candidate_lower = candidate.lower()
    symbol_lower = symbol.lower()
    if symbol_lower in candidate_lower:
        return True
    path = PurePosixPath(candidate)
    names = {path.name.lower(), path.stem.lower()}
    if symbol_lower in names:
        return True
    return fnmatch.fnmatch(symbol_lower, candidate_lower) or fnmatch.fnmatch(
        candidate_lower, symbol_lower
    )


def _format_ref_hits(hits: list[RefHit]) -> list[str]:
    if not hits:
        return ["  (none)"]
    return [f"  {hit.doc_id} {hit.path}:{hit.line}" for hit in hits]


def _format_symbol_hits(hits: list[SymbolHit]) -> list[str]:
    if not hits:
        return ["  (none)"]
    return [f"  {hit.doc_id} {hit.path}:{hit.line} {hit.match}" for hit in hits]


def _ref_hit_to_dict(hit: RefHit) -> dict[str, object]:
    return {"doc_id": hit.doc_id, "path": hit.path, "line": hit.line}


def _symbol_hit_to_dict(hit: SymbolHit) -> dict[str, object]:
    return {
        "doc_id": hit.doc_id,
        "path": hit.path,
        "line": hit.line,
        "match": hit.match,
    }
