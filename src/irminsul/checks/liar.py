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
  with the ``init`` command. Other kinds match their identity exactly.
- Only `explanation`/`reference` docs are scanned — that is where enumerating a
  surface *as documentation* is the anti-pattern. Tutorials/howtos demonstrate
  commands; ADRs and meta docs name them as narrative; none are flagged.
- A doc that declares an `inventory:` block of a kind has opted into governance and
  is not flagged for that kind.

The surface is sourced from the Artifact-2 extractors, not any committed reference.
"""

from __future__ import annotations

import re
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import AudienceEnum, StatusEnum
from irminsul.inventory import KNOWN_KINDS, get_extractor

_THRESHOLD = 3
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_SCANNED_AUDIENCES = {AudienceEnum.explanation, AudienceEnum.reference}


def _matches(kind: str, span: str, identity: str) -> bool:
    if kind == "cli":
        # the invoked form ("<prog> <identity>"), never a bare token
        return span != identity and span.endswith(f" {identity}")
    return span == identity


class LiarCheck:
    name: ClassVar[str] = "liar"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files, _ = walk_source_files(graph.repo_root, graph.config.paths.source_roots)
        surfaces: dict[str, set[str]] = {}
        for kind in KNOWN_KINDS:
            extractor = get_extractor(kind, graph.config)
            if extractor is None:
                continue
            identities = {item.identity for item in extractor.extract(source_files, graph.config)}
            if identities:
                surfaces[kind] = identities
        if not surfaces:
            return []

        out: list[Finding] = []
        for node in graph.nodes.values():
            if node.frontmatter.status != StatusEnum.stable:
                continue
            if node.frontmatter.audience not in _SCANNED_AUDIENCES:
                continue
            if _is_rfc(node):
                continue

            declared_kinds = {entry.kind for entry in node.frontmatter.inventory}
            hits = self._scan(node.body, surfaces, declared_kinds)
            for kind, found in hits.items():
                if len(found) >= _THRESHOLD:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=self.default_severity,
                            message=(
                                f"prose enumerates {len(found)} '{kind}' items that are "
                                "derivable from code"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            line=min(found.values()),
                            suggestion=(
                                f"declare a curated `inventory:` block of kind {kind}, or "
                                f"link to the derivation (`irminsul surface {kind}`)"
                            ),
                        )
                    )
        return out

    def _scan(
        self, body: str, surfaces: dict[str, set[str]], declared_kinds: set[str]
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
                    if any(_matches(kind, span, identity) for span in spans):
                        found.setdefault(kind, {})[identity] = lineno
        return found


def _is_rfc(node: DocNode) -> bool:
    return "/rfcs/" in node.path.as_posix()
