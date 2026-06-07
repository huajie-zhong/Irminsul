"""InventoryDriftCheck — curated-intent inventory must not name code that is gone.

Under "derive, don't materialize" a doc never mirrors a complete code surface; it
may declare a *curated subset* (`inventory:` frontmatter) of items it deliberately
calls out. This check verifies each declared item still exists in the code — the
anti-lie direction only. It never flags items that exist in code but are absent from
the inventory (that would be the completeness/materialization pressure the principle
rejects); the on-demand `irminsul surface` query is how you see the full surface.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Fix, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter_edit import remove_inventory_item
from irminsul.inventory import get_extractor


def _item_remover(kind: str, item: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return remove_inventory_item(text, kind, item)

    return apply


class InventoryDriftCheck:
    name: ClassVar[str] = "inventory-drift"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files, _ = walk_source_files(graph.repo_root, graph.config.paths.source_roots)
        cache: dict[tuple[str, tuple[str, ...]], set[str]] = {}
        out: list[Finding] = []

        for node in graph.nodes.values():
            for entry in node.frontmatter.inventory:
                extractor = get_extractor(entry.kind, graph.config)
                if extractor is None:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.info,
                            message=(
                                f"inventory kind '{entry.kind}' has no extractor "
                                "(built-in: cli, http, exports, env-vars; or a generic rule)"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion="Use a known kind or declare a generic rule in irminsul.toml",
                        )
                    )
                    continue

                globs = [entry.source] if entry.source else list(node.frontmatter.describes)
                if not globs:
                    out.append(
                        Finding(
                            check=self.name,
                            severity=Severity.info,
                            message=(
                                f"inventory ({entry.kind}) has no 'source' and the doc "
                                "declares no 'describes' to extract from"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion="Add a 'source' glob to the inventory entry",
                        )
                    )
                    continue

                key = (entry.kind, tuple(globs))
                identities = cache.get(key)
                if identities is None:
                    spec = GitIgnoreSpec.from_lines(globs)
                    matched = [(p, d) for p, d in source_files if spec.match_file(d)]
                    identities = {
                        item.identity for item in extractor.extract(matched, graph.config)
                    }
                    cache[key] = identities

                for item in entry.items:
                    if item not in identities:
                        out.append(
                            Finding(
                                check=self.name,
                                severity=self.default_severity,
                                message=(
                                    f"inventory lists {entry.kind} '{item}' but it was "
                                    "not found in the code it describes"
                                ),
                                path=node.path,
                                doc_id=node.id,
                                suggestion=(
                                    "Remove the item, fix its identity, or check the "
                                    "'source' glob; see `irminsul surface "
                                    f"{entry.kind}`"
                                ),
                            )
                        )

        return out

    def _missing_items(self, graph: DocGraph) -> Iterator[tuple[DocNode, str, str]]:
        """Yield (node, kind, item) for every declared inventory item gone from code."""
        if graph.config is None or graph.repo_root is None:
            return

        source_files, _ = walk_source_files(graph.repo_root, graph.config.paths.source_roots)
        cache: dict[tuple[str, tuple[str, ...]], set[str]] = {}

        for node in graph.nodes.values():
            for entry in node.frontmatter.inventory:
                extractor = get_extractor(entry.kind, graph.config)
                if extractor is None:
                    continue
                globs = [entry.source] if entry.source else list(node.frontmatter.describes)
                if not globs:
                    continue

                key = (entry.kind, tuple(globs))
                identities = cache.get(key)
                if identities is None:
                    spec = GitIgnoreSpec.from_lines(globs)
                    matched = [(p, d) for p, d in source_files if spec.match_file(d)]
                    identities = {
                        item.identity for item in extractor.extract(matched, graph.config)
                    }
                    cache[key] = identities

                for item in entry.items:
                    if item not in identities:
                        yield node, entry.kind, item

    def fixes(self, findings: list[Finding], graph: DocGraph) -> list[Fix]:
        """Drop drifted items from the `inventory:` block (RFC 0020).

        Removes curated content, so it requires `--confirm`. Gated on the nodes
        that produced a drift finding.
        """
        fixable = {
            finding.doc_id
            for finding in findings
            if finding.check == self.name and finding.severity == self.default_severity
        }
        if not fixable:
            return []

        out: list[Fix] = []
        for node, kind, item in self._missing_items(graph):
            if node.id not in fixable:
                continue
            out.append(
                Fix(
                    path=node.path,
                    description=f"remove {kind} '{item}' from inventory in {node.path.as_posix()}",
                    apply=_item_remover(kind, item),
                    requires_confirm=True,
                )
            )
        return out
