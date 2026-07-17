"""InventoryDriftCheck — keep a doc's `inventory:` honest against the live surface.

Under "derive, don't materialize" a doc never mirrors a complete code surface; it
may declare a *curated subset* (`inventory:` frontmatter) of items it deliberately
calls out. By default this check only verifies each declared item still exists in
code — the anti-lie direction (RFC 0020). It never demands completeness unless the
entry opts in.

An entry may opt into being a *watched surface* (RFC 0027), gaining the other two
directions: with `complete: true` every live identity must be either declared
(`items`) or deliberately excluded (`omit`), so a *new* surface element is flagged;
with `fingerprints` each item's AST-normalized code shape is pinned (reusing the
`irminsul.anchors` hashing behind `claim-anchor`), so a behavior change to a
still-named item is flagged for re-read and re-pin.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.anchors import Anchor, resolve
from irminsul.checks.base import Finding, Fix, Severity
from irminsul.checks.globs import walk_configured_source_files
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import InventoryEntry
from irminsul.frontmatter_edit import remove_inventory_item
from irminsul.inventory import SurfaceItem, get_extractor


def _item_remover(kind: str, item: str) -> Callable[[str], str]:
    def apply(text: str) -> str:
        return remove_inventory_item(text, kind, item)

    return apply


CODE_NO_EXTRACTOR = "inventory-drift/no-extractor"
CODE_NO_SOURCE_GLOB = "inventory-drift/no-source-glob"
CODE_ITEM_NOT_FOUND = "inventory-drift/item-not-found"
CODE_UNDECLARED_LIVE_ITEM = "inventory-drift/undeclared-live-item"
CODE_STALE_OMIT = "inventory-drift/stale-omit"
CODE_UNFINGERPRINTABLE = "inventory-drift/unfingerprintable"
CODE_FINGERPRINT_UNRESOLVED = "inventory-drift/fingerprint-unresolved"
CODE_FINGERPRINT_DRIFT = "inventory-drift/fingerprint-drift"


class InventoryDriftCheck:
    name: ClassVar[str] = "inventory-drift"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_NO_EXTRACTOR: (
            "An `inventory:` entry names a kind with no registered extractor. Use a "
            "known kind (cli, http, exports, env-vars, mcp), or declare a generic rule "
            "in irminsul.toml."
        ),
        CODE_NO_SOURCE_GLOB: (
            "An `inventory:` entry has no `source` glob and the doc declares no "
            "`describes` to extract from. Add a `source` glob to the entry."
        ),
        CODE_ITEM_NOT_FOUND: (
            "An inventory `items` entry no longer exists in the code it describes. "
            "Remove it, fix its identity, or check the `source` glob."
        ),
        CODE_UNDECLARED_LIVE_ITEM: (
            "A `complete: true` (watched) inventory entry has a live identity that is "
            "neither listed in `items` nor `omit`. Document it or add it to `omit`."
        ),
        CODE_STALE_OMIT: (
            "An inventory `omit` entry names an identity that is no longer in the live "
            "surface. Remove it from `omit`."
        ),
        CODE_UNFINGERPRINTABLE: (
            "A fingerprinted inventory item has no resolvable code symbol, so it can't "
            "be fingerprinted. Remove its fingerprint, or use a kind that resolves "
            "symbols."
        ),
        CODE_FINGERPRINT_UNRESOLVED: (
            "A fingerprinted inventory item's symbol could not be resolved. Check the "
            "source path, or remove its fingerprint."
        ),
        CODE_FINGERPRINT_DRIFT: (
            "A fingerprinted inventory item's code shape changed since it was pinned. "
            "Re-read its docs, then run `irminsul anchors --re-pin`."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files = walk_configured_source_files(graph.repo_root, graph.config).files
        cache: dict[tuple[str, tuple[str, ...]], dict[str, SurfaceItem]] = {}
        out: list[Finding] = []

        for node in graph.nodes.values():
            for entry in node.frontmatter.inventory:
                extractor = get_extractor(entry.kind, graph.config)
                if extractor is None:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_NO_EXTRACTOR,
                            severity=Severity.info,
                            message=(
                                f"inventory kind '{entry.kind}' has no extractor "
                                "(built-in: cli, http, exports, env-vars, mcp; or a generic rule)"
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
                            code=CODE_NO_SOURCE_GLOB,
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
                by_identity = cache.get(key)
                if by_identity is None:
                    spec = GitIgnoreSpec.from_lines(globs)
                    matched = [(p, d) for p, d in source_files if spec.match_file(d)]
                    by_identity = {
                        item.identity: item for item in extractor.extract(matched, graph.config)
                    }
                    cache[key] = by_identity

                out.extend(self._check_entry(graph, node, entry, by_identity))

        return out

    def _check_entry(
        self,
        graph: DocGraph,
        node: DocNode,
        entry: InventoryEntry,
        by_identity: dict[str, SurfaceItem],
    ) -> list[Finding]:
        assert graph.repo_root is not None
        out: list[Finding] = []

        # Accuracy (default): a declared item must still exist in code.
        for item in entry.items:
            if item not in by_identity:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_ITEM_NOT_FOUND,
                        severity=self.default_severity,
                        message=(
                            f"inventory lists {entry.kind} '{item}' but it was "
                            "not found in the code it describes"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion=(
                            "Remove the item, fix its identity, or check the "
                            f"'source' glob; see `irminsul surface {entry.kind}`"
                        ),
                    )
                )

        # Completeness (opt-in): every live identity must be declared or omitted.
        if entry.complete:
            declared = set(entry.items) | set(entry.omit)
            for identity in sorted(by_identity):
                if identity not in declared:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNDECLARED_LIVE_ITEM,
                            severity=self.default_severity,
                            message=(
                                f"{entry.kind} '{identity}' exists in code but the "
                                "watched inventory neither lists nor omits it"
                            ),
                            path=node.path,
                            doc_id=node.id,
                            suggestion=(
                                f"Document it in 'items', or add it to 'omit'; see "
                                f"`irminsul surface {entry.kind}`"
                            ),
                        )
                    )

        # An omit entry that no longer names anything live is stale.
        for omitted in entry.omit:
            if omitted not in by_identity:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_STALE_OMIT,
                        severity=self.default_severity,
                        message=(
                            f"inventory omits {entry.kind} '{omitted}' but it is not "
                            "in the live surface"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Remove it from 'omit'",
                    )
                )

        # Freshness (opt-in): a pinned item whose code shape changed must be re-read.
        for identity, pinned in entry.fingerprints.items():
            live = by_identity.get(identity)
            if live is None:
                continue  # covered by the accuracy/completeness directions above
            if live.symbol is None:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_UNFINGERPRINTABLE,
                        severity=Severity.info,
                        message=(
                            f"{entry.kind} '{identity}' cannot be fingerprinted "
                            "(no resolvable code symbol)"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Remove its fingerprint, or use a kind that resolves symbols",
                    )
                )
                continue
            sym_path, _, sym_name = live.symbol.partition("#")
            resolution = resolve(
                graph.repo_root,
                Anchor(line=0, raw="", path=sym_path, symbol=sym_name or None, pinned=pinned),
            )
            if resolution.status != "ok" or resolution.current is None:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_FINGERPRINT_UNRESOLVED,
                        severity=Severity.info,
                        message=(
                            f"{entry.kind} '{identity}' fingerprint could not be "
                            f"resolved ({resolution.status})"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Check the source path, or remove its fingerprint",
                    )
                )
                continue
            if resolution.current != pinned:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_FINGERPRINT_DRIFT,
                        severity=self.default_severity,
                        message=(
                            f"{entry.kind} '{identity}' changed since its fingerprint "
                            "was pinned; re-read its docs and re-pin"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Re-read the item's docs, then run `irminsul anchors --re-pin`",
                    )
                )

        return out

    def _missing_items(self, graph: DocGraph) -> Iterator[tuple[DocNode, str, str]]:
        """Yield (node, kind, item) for every declared inventory item gone from code."""
        if graph.config is None or graph.repo_root is None:
            return

        source_files = walk_configured_source_files(graph.repo_root, graph.config).files
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
