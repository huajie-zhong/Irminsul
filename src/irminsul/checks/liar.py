"""LiarCheck — a doc must not hand-enumerate a derivable code surface in prose.

"Derive, don't materialize": a complete list of commands / endpoints / exports /
env vars is reconstructable from code, so restating it in prose creates a cache
that goes stale (the `regen agents-md` incident). This check flags a doc that names
at least `_THRESHOLD` distinct identities of a single derived surface `kind`, and
tells the author to either declare a curated `inventory:` subset (which
`inventory-drift` then keeps honest) or link to the on-demand derivation
(`irminsul surface <kind>`).

Precision choices that keep false positives low:

- Counting is per-doc across all backtick code spans, so an enumeration spread over
  headings and paragraphs (not just a list) is still caught.
- For `cli`, a span must be the *invoked* form (``irminsul regen agents-md``), not a
  bare token — otherwise a component link like ``[init](init.md)`` would collide
  with the ``init`` command — and when the project's program names are known it must
  invoke one of them, so ``git status`` is not the ``status`` command. Other kinds match
  their identity exactly.
- Guides, RFCs, and decision records are not scanned: enumerating a surface *as
  documentation* is the anti-pattern, while a guide demonstrates commands step by step
  and a record names them as narrative.
- A doc that declares an `inventory:` block of a kind has opted into governance and
  is not flagged for that kind.
- Kinds that docs name in passing (options, check names, config keys) are not counted
  across the doc; only a single list or table naming `_BLOCK_THRESHOLD` or more of them
  is an enumeration.

The surface is sourced from the static surface extractors, not any committed reference.
"""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.globs import walk_configured_source_files
from irminsul.config import IrminsulConfig, in_layer
from irminsul.docgraph import DocGraph, DocNode, is_decision, is_rfc
from irminsul.frontmatter import StatusEnum
from irminsul.inventory import available_kinds, get_extractor, kind_capabilities
from irminsul.inventory.programs import program_names

_THRESHOLD = 3
_BLOCK_THRESHOLD = 5
_BLOCK_LINE_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")
_DISTINCTIVE_RE = re.compile(r"^[A-Za-z0-9-]*[-_.][A-Za-z0-9_.-]*[A-Za-z0-9]$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _matches(command_path: bool, span: str, identity: str, programs: tuple[str, ...] = ()) -> bool:
    if command_path:
        # the invoked form ("<prog> <identity>"), never a bare token; when the project's
        # program names are known, `git status` is not this project's `status`
        if span == identity or not span.endswith(f" {identity}"):
            return False
        return not programs or span.split(maxsplit=1)[0] in programs
    return span == identity


CODE_DERIVABLE_ENUMERATION = "liar/derivable-enumeration"


class LiarCheck:
    name: ClassVar[str] = "liar"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_DERIVABLE_ENUMERATION: (
            "This doc's prose hand-enumerates a derivable code surface (commands, "
            "endpoints, exports, env vars) instead of linking to it. Declare a curated "
            "`inventory:` subset, or link to `irminsul surface <kind>`."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_DERIVABLE_ENUMERATION: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files = walk_configured_source_files(graph.repo_root, graph.config).files
        surfaces: dict[str, set[str]] = {}
        named_in_passing: dict[str, set[str]] = {}
        command_paths: set[str] = set()
        for kind in available_kinds(graph.config):
            capabilities = kind_capabilities(kind, graph.config)
            if capabilities.command_path:
                command_paths.add(kind)
            extractor = get_extractor(kind, graph.config)
            if extractor is None:
                continue
            identities = {item.identity for item in extractor.extract(source_files, graph.config)}
            if identities:
                target = named_in_passing if capabilities.prose_named else surfaces
                target[kind] = identities
        if not surfaces and not named_in_passing:
            return []

        programs = program_names(graph.repo_root, graph.config)
        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.status != StatusEnum.stable:
                continue
            if (
                is_rfc(node, graph.config)
                or is_decision(node, graph.config)
                or in_layer(graph.config or IrminsulConfig(), node.path, "guides")
            ):
                continue

            declared_kinds = {entry.kind for entry in node.frontmatter.inventory}
            hits = self._scan(node.body, surfaces, declared_kinds, command_paths, programs)
            for kind, found in hits.items():
                if len(found) >= _THRESHOLD:
                    out.append(self._finding(node, kind, found, "prose"))
            for kind, found in self._scan_blocks(
                node.body, named_in_passing, declared_kinds
            ).items():
                out.append(self._finding(node, kind, found, "a list or table"))
        return out

    def _finding(self, node: DocNode, kind: str, found: dict[str, int], where: str) -> Finding:
        return Finding(
            check=self.name,
            code=CODE_DERIVABLE_ENUMERATION,
            severity=self.default_severity,
            message=f"{where} enumerates {len(found)} '{kind}' items that are derivable from code",
            path=node.path,
            doc_id=node.id,
            line=node.file_line(min(found.values())),
            suggestion=(
                f"declare a curated `inventory:` block of kind {kind}, or "
                f"link to the derivation (`irminsul surface {kind}`)"
            ),
        )

    def _scan_blocks(
        self, body: str, surfaces: dict[str, set[str]], declared_kinds: set[str]
    ) -> dict[str, dict[str, int]]:
        """Per kind, the largest single list or table naming enough identities of it."""
        blocks: list[list[tuple[int, str]]] = []
        current: list[tuple[int, str]] = []
        in_fence = False
        for lineno, line in enumerate(body.splitlines(), start=1):
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if not in_fence and _BLOCK_LINE_RE.match(line):
                current.append((lineno, line))
                continue
            if current:
                blocks.append(current)
                current = []
        if current:
            blocks.append(current)

        out: dict[str, dict[str, int]] = {}
        for kind, identities in surfaces.items():
            if kind in declared_kinds:
                continue
            for block in blocks:
                found: dict[str, int] = {}
                for lineno, line in block:
                    for span in _BACKTICK_RE.findall(line):
                        if span in identities and span not in found and _DISTINCTIVE_RE.match(span):
                            found[span] = lineno
                if len(found) >= _BLOCK_THRESHOLD and len(found) > len(out.get(kind, {})):
                    out[kind] = found
        return out

    def _scan(
        self,
        body: str,
        surfaces: dict[str, set[str]],
        declared_kinds: set[str],
        command_paths: set[str],
        programs: tuple[str, ...],
    ) -> dict[str, dict[str, int]]:
        """Per kind, map each matched identity to the first body line it appears on."""
        found: dict[str, dict[str, int]] = {}
        in_fence = False
        for lineno, line in enumerate(body.splitlines(), start=1):
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            spans = _BACKTICK_RE.findall(line)
            if not spans:
                continue
            for kind, identities in surfaces.items():
                if kind in declared_kinds:
                    continue
                for identity in identities:
                    if identity in found.get(kind, {}):
                        continue
                    if any(
                        _matches(kind in command_paths, span, identity, programs) for span in spans
                    ):
                        found.setdefault(kind, {})[identity] = lineno
        return found
