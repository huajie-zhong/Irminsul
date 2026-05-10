"""Deterministic doc-reality audits from RFC 0009."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.config import TerminologyRule
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import StatusEnum
from irminsul.regen.doc_surfaces import surface_by_filename

_LOCAL_MD_RE = re.compile(r"(?<![\w.-])((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.md)(?![\w.-])")
_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\n]*\](?:\([^\)\n]*\)|\[[^\]\n]*\])")
_LINK_DEFINITION_RE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s+\S+")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_IGNORE_RE = re.compile(r"irminsul:ignore\s+prose-file-reference")
_IGNORE_START_RE = re.compile(r"irminsul:ignore-start\s+prose-file-reference")
_IGNORE_END_RE = re.compile(r"irminsul:ignore-end\s+prose-file-reference")


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


def _line_link_spans(line: str) -> list[range]:
    if _LINK_DEFINITION_RE.match(line):
        return [range(0, len(line))]
    return [range(match.start(), match.end()) for match in _MARKDOWN_LINK_RE.finditer(line)]


def _inside_any(pos: int, spans: list[range]) -> bool:
    return any(pos in span for span in spans)


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
