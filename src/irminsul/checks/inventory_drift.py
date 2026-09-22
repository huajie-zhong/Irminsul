"""InventoryDriftCheck — keep a doc's `inventory:` honest against the live surface.

Under "derive, don't materialize" a doc never mirrors a complete code surface; it
may declare a *curated subset* (`inventory:` frontmatter) of items it deliberately
calls out. By default this check only verifies each declared item still exists in
code — the anti-lie direction. It never demands completeness unless the
entry opts in.

An entry may opt into being a *watched surface*, gaining the other two
directions: with `complete: true` every live identity must be either declared
(`items`) or deliberately excluded (`omit`), so a *new* surface element is flagged;
with `fingerprints` each item's AST-normalized code shape is pinned (reusing the
`irminsul.anchors` hashing behind `claim-anchor`), so a behavior change to a
still-named item is flagged for re-read and re-pin.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import ClassVar, Final

from pathspec import GitIgnoreSpec

from irminsul.anchors import Anchor, resolve
from irminsul.checks.base import Finding, FindingClass, Fix, Severity
from irminsul.checks.code_spans import CodeSpan, code_spans, is_live_doc, mention_regex, names_token
from irminsul.checks.globs import walk_configured_source_files
from irminsul.docgraph import DocGraph, DocNode
from irminsul.frontmatter import InventoryEntry
from irminsul.frontmatter_edit import remove_inventory_item
from irminsul.inventory import KNOWN_KINDS_TEXT, SurfaceItem, get_extractor, kind_capabilities
from irminsul.inventory.programs import program_names


def _foreign_head(text: str, programs: tuple[str, ...]) -> str | None:
    """The program this code span invokes, when it is not one of ours.

    `None` means nothing else can own what the span names: it opens with a flag, with one
    of this project's own program names, or with nothing at all. Otherwise the span is an
    invocation of somebody else's program, and the arguments after that program name
    describe *its* surface — the `--upgrade` in `pip install --upgrade irminsul` is pip's,
    and measuring it against our inventory reports a true sentence as a lie.

    When the project's own program names are unknown, an invocation cannot be attributed
    to anyone, and a certain finding needs better ground than a guess;
    `frameworks.command_names` supplies them where no package manifest does.

    Comparing the first token to the program names literally was too blunt: our own CLI is
    documented as `python -m irminsul`, `uv run irminsul` and `.venv\\Scripts\\irminsul`,
    and each of those read as somebody else's program, so the flags after them stopped
    being measured at all. `_invoked_program` sees through a launcher and a path before the
    comparison.
    """
    tokens = text.strip().lstrip("$#").split()
    if not tokens or tokens[0].startswith("-"):
        return None
    if _is_assignment(tokens):
        # `enabled = ["--gone"]` in a TOML or YAML example invokes nothing, so there is no
        # other program for its flags to belong to.
        return None
    invoked = _invoked_program(tokens)
    return None if invoked is None or invoked in programs else invoked


#: Commands that run *another* command, so the program being invoked is further along.
_LAUNCHERS: Final = frozenset(
    {
        "uv",
        "uvx",
        "npx",
        "pipx",
        "poetry",
        "pdm",
        "hatch",
        "rye",
        "pnpm",
        "yarn",
        "npm",
        "sudo",
        "env",
        "time",
        "nice",
        "xargs",
    }
)
#: Words a launcher puts between itself and the program.
_LAUNCHER_VERBS: Final = frozenset({"run", "exec", "--"})


def _basename(token: str) -> str:
    """The command name in a token that may be a path: `.venv/Scripts/irminsul.exe`."""
    name = token.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".exe") else name


def _is_assignment(tokens: list[str]) -> bool:
    return "=" in tokens[:2] or "=" in tokens[0] or tokens[0].endswith(":")


def _invoked_program(tokens: list[str]) -> str | None:
    """The program a command line actually runs, seen through launchers and paths.

    `None` when the line runs nothing identifiable. Deliberately shallow — three shapes,
    each one a spelling this project's own documentation uses — rather than an attempt to
    understand shell.
    """
    index = 0
    while index < len(tokens):
        head = _basename(tokens[index])
        if head.startswith("python") or head == "py":
            # `python -m irminsul check`, and `py -3.12 -m irminsul check`.
            for offset in range(index + 1, len(tokens)):
                token = tokens[offset]
                if token == "-m" and offset + 1 < len(tokens):
                    return _basename(tokens[offset + 1])
                if not token.startswith("-"):
                    return _basename(token)
            return head
        if head in _LAUNCHERS:
            index += 1
            while index < len(tokens) and (
                tokens[index].startswith("-") or tokens[index] in _LAUNCHER_VERBS
            ):
                index += 1
            continue
        return head
    return None


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
CODE_UNEXPLAINED_LIVE_ITEM = "inventory-drift/unexplained-live-item"
CODE_UNKNOWN_MENTION = "inventory-drift/unknown-mention"


class InventoryDriftCheck:
    name: ClassVar[str] = "inventory-drift"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_NO_EXTRACTOR: (
            "An `inventory:` entry names a kind with no registered extractor. Use a "
            f"known kind ({KNOWN_KINDS_TEXT}), or declare a generic rule "
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
        CODE_UNEXPLAINED_LIVE_ITEM: (
            "An `explained_in` inventory entry has a live identity that no code span names: "
            "in the declaring doc for `explained_in: self`, in any stable live doc for "
            "`explained_in: any`. Explain it where a reader would look, or add it to `omit`."
        ),
        CODE_UNKNOWN_MENTION: (
            "A doc in the scope of an explained entry names, in a code span, something shaped "
            "like an identity of that kind (by the kind's mention pattern) that the code does "
            "not declare. Correct it, or list another tool's identity under `foreign`."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_NO_EXTRACTOR: FindingClass.certain,
        CODE_NO_SOURCE_GLOB: FindingClass.certain,
        CODE_ITEM_NOT_FOUND: FindingClass.certain,
        CODE_UNDECLARED_LIVE_ITEM: FindingClass.certain,
        CODE_STALE_OMIT: FindingClass.certain,
        CODE_UNFINGERPRINTABLE: FindingClass.hint,
        CODE_FINGERPRINT_UNRESOLVED: FindingClass.hint,
        CODE_FINGERPRINT_DRIFT: FindingClass.hint,
        CODE_UNEXPLAINED_LIVE_ITEM: FindingClass.certain,
        CODE_UNKNOWN_MENTION: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files = walk_configured_source_files(graph.repo_root, graph.config).files
        cache: dict[tuple[str, tuple[str, ...]], dict[str, SurfaceItem]] = {}
        self._spans: dict[str, list[CodeSpan]] = {}
        self._programs = program_names(graph.repo_root, graph.config)
        out: list[Finding] = []

        for node in graph.nodes.values():
            for entry in node.frontmatter.inventory:
                extractor = get_extractor(entry.kind, graph.config)
                if extractor is None:
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_NO_EXTRACTOR,
                            severity=Severity.error,
                            message=(
                                f"inventory kind '{entry.kind}' has no extractor "
                                f"(built-in: {KNOWN_KINDS_TEXT}; or a generic rule)"
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
                            severity=Severity.error,
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
                        severity=Severity.error,
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
                            severity=Severity.error,
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
                        severity=Severity.error,
                        message=(
                            f"inventory omits {entry.kind} '{omitted}' but it is not "
                            "in the live surface"
                        ),
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Remove it from 'omit'",
                    )
                )

        if entry.explained_in is not None:
            out.extend(self._explained_findings(graph, node, entry, by_identity))

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

    def _spans_for(self, node: DocNode) -> list[CodeSpan]:
        key = node.path.as_posix()
        spans = self._spans.get(key)
        if spans is None:
            spans = code_spans(node.body)
            self._spans[key] = spans
        return spans

    def _attributed_spans(self, node: DocNode) -> Iterator[tuple[CodeSpan, str | None]]:
        """Each of this doc's code spans, with the foreign program it invokes, if any.

        A fenced command wrapped over several lines arrives here as one span per line,
        and the later lines carry no program name of their own, so each inherits the
        program decided for the line that continued onto it.
        """
        inherited: str | None = None
        carrying = False
        for span in self._spans_for(node):
            text = span.text.strip()
            foreign = inherited if carrying else _foreign_head(text, self._programs)
            carrying = text.endswith("\\")
            inherited = foreign
            yield span, foreign

    def _explained_findings(
        self,
        graph: DocGraph,
        node: DocNode,
        entry: InventoryEntry,
        by_identity: dict[str, SurfaceItem],
    ) -> list[Finding]:
        scope = (
            [node]
            if entry.explained_in == "self"
            else [n for n in graph.nodes.values() if n is node or is_live_doc(n, graph.config)]
        )
        where = "this doc" if entry.explained_in == "self" else "any live doc"
        spans = [span for doc in scope for span in self._spans_for(doc)]
        out: list[Finding] = []
        omitted = set(entry.omit)
        for identity in sorted(by_identity):
            if identity in omitted or names_token(spans, identity):
                continue
            item = by_identity[identity]
            defined = f" (defined at {item.display}:{item.line})" if item.display else ""
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_UNEXPLAINED_LIVE_ITEM,
                    severity=Severity.error,
                    message=(
                        f"{entry.kind} '{identity}' exists in code but no code span in "
                        f"{where} names it{defined}"
                    ),
                    path=node.path,
                    doc_id=node.id,
                    suggestion=f"Explain `{identity}` in the docs, or add it to 'omit'",
                    data={
                        "problem": "unexplained-live-item",
                        "kind": entry.kind,
                        "identity": identity,
                    },
                )
            )

        assert graph.config is not None
        capabilities = kind_capabilities(entry.kind, graph.config)
        if not capabilities.mention_patterns:
            return out
        mentions = [mention_regex(pattern) for pattern in capabilities.mention_patterns]
        known = set(by_identity) | set(entry.foreign)
        reported: set[tuple[str, str]] = set()
        for doc in scope:
            for span, foreign in self._attributed_spans(doc):
                for match in (m for regex in mentions for m in regex.finditer(span.text)):
                    flag = match.group(0)
                    if foreign is not None and flag not in foreign:
                        # An argument of somebody else's command describes their surface.
                        # The head token itself is exempt: a span that *is* the identity
                        # invokes nothing, whatever its shape.
                        continue
                    if flag in known or (doc.path.as_posix(), flag) in reported:
                        continue
                    reported.add((doc.path.as_posix(), flag))
                    out.append(
                        Finding(
                            check=self.name,
                            code=CODE_UNKNOWN_MENTION,
                            severity=Severity.error,
                            message=f"code span names {entry.kind} '{flag}' but the code does not declare it",
                            path=doc.path,
                            doc_id=doc.id,
                            line=doc.file_line(span.body_line),
                            suggestion=(
                                f"Correct it, or list it under 'foreign' in {node.path.as_posix()}"
                            ),
                            data={"problem": "unknown-mention", "identity": flag},
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
        """Drop drifted items from the `inventory:` block.

        Removes curated content, so it requires `--confirm`. Gated on the nodes
        that produced a drift finding.
        """
        fixable = {finding.doc_id for finding in findings if finding.code == CODE_ITEM_NOT_FOUND}
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
