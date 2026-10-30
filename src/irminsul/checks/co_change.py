"""Co-change enforcement — docs ship in the same change as the code they claim.

A pass, not a registered graph check: it needs the changed-file set of the range on the
graph, from the merge base to the working tree, which only `--diff <base>` or
`context --after-edit` with a base supplies. It reads the diff itself, where
`mtime-drift` compares commit times. Ownership is resolved through the exact `describes`
glob logic the uniqueness check uses (`resolve_claims` / `most_specific_claims`), so "who
owns this file?" has one answer everywhere. Findings are hints, so `--fail-on hint` makes
them fail the run like any other hint.

A reader who re-reads the doc and finds it still right signs the warning off with an
`Irminsul-Reviewed` trailer in the change. This pass reports the warning, with the doc as
its subject and the claimed sources as what a later change lapses; the acknowledgement
step reads the trailer (`irminsul.checks.acknowledgement`). An ignore comment cannot do
this: the finding has no line, and adding the comment would itself be the doc edit the
check asks for.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

from irminsul.checks.acknowledgement import shown_path
from irminsul.checks.base import Answer, Finding, FindingClass, Severity
from irminsul.checks.change_range import after_text
from irminsul.checks.uniqueness import most_specific_claims, resolve_claims
from irminsul.docgraph import ChangeRange, DocGraph, DocNode

if TYPE_CHECKING:
    from irminsul.git.reader import GitReader

CHECK_NAME: Final = "co-change"
CODE_UNREFLECTED_CHANGE: Final = "co-change/unreflected-change"


class CoChangePass:
    """Docs must ship in the same change as the code they claim.

    It judges the change rather than the tree, so it reports only when the CLI's `--diff`
    flag puts a range on the graph.
    """

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNREFLECTED_CHANGE: (
            "A source file this doc claims via `describes` changed in the diff, but "
            "the doc itself did not. Update the doc in the same change, or run "
            "`irminsul context <changed-file>` to see what it claims."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNREFLECTED_CHANGE: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_UNREFLECTED_CHANGE: Answer.trailer(
            "if you re-read the doc and it is still right, add this trailer"
        ),
    }

    def run(self, graph: DocGraph, selected: Collection[str]) -> list[Finding]:
        change, repo_root = graph.change, graph.repo_root
        if change is None or repo_root is None:
            return []
        return run_co_change(
            graph,
            change.changed,
            whitespace_only_docs(graph.git, repo_root, change),
            change.uncommitted,
        )


def whitespace_only_docs(git: GitReader, repo_root: Path, change: ChangeRange) -> frozenset[str]:
    """The changed docs whose content differs from the merge base only in whitespace."""
    from irminsul.git.changes import GitChangesError, file_at_ref

    def words(text: str) -> str:
        return " ".join(text.split())

    out: set[str] = set()
    for path in change.changed:
        if not path.endswith(".md"):
            continue
        try:
            before = file_at_ref(git, repo_root, change.merge_base, path)
        except GitChangesError:
            continue
        after = after_text(git, repo_root, change.head, path)
        if before is not None and after is not None and words(before) == words(after):
            out.add(path)
    return frozenset(out)


def run_co_change(
    graph: DocGraph,
    changed: frozenset[str],
    cosmetic: frozenset[str] = frozenset(),
    uncommitted: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Warn for each owning doc whose claimed sources changed without it.

    `changed` is the repo-relative POSIX path set from `git diff --name-only`, and
    `uncommitted` the part of it no commit holds yet, which a warning marks so the reader
    knows the trailer belongs in the commit that will carry those files.
    A changed source file is "unreflected" when none of its most-specific
    owning docs appear in the changed set; findings are grouped per owning
    doc, listing every unreflected file it claims.

    `cosmetic` names docs whose change was whitespace only. They do not count as
    having shipped with the code: one blank line in the owning doc would otherwise
    satisfy this check, making the cheapest way to pass it an edit that says nothing.
    """
    if graph.config is None or graph.repo_root is None:
        return []

    # Resolve claims against the changed set directly rather than walking the
    # whole source tree: faster on large repos, and a deleted claimed file
    # (absent from any walk) still triggers enforcement on its owning doc.
    claims_by_file = resolve_claims(graph, sorted(changed))

    unreflected_by_doc: dict[str, tuple[DocNode, list[str]]] = {}
    for source_file in sorted(changed):
        claims = claims_by_file.get(source_file)
        if not claims:
            continue  # unclaimed file — nothing owns it, nothing to enforce
        owners = {node.path.as_posix(): node for node, _, _ in most_specific_claims(claims)}
        if any(doc_path in changed and doc_path not in cosmetic for doc_path in owners):
            continue  # an owning doc shipped in the same change
        for doc_path, node in owners.items():
            _, files = unreflected_by_doc.setdefault(doc_path, (node, []))
            files.append(source_file)

    out: list[Finding] = []
    for doc_path in sorted(unreflected_by_doc):
        node, files = unreflected_by_doc[doc_path]
        shown = ", ".join(shown_path(path, uncommitted) for path in files)
        out.append(
            Finding(
                check=CHECK_NAME,
                code=CODE_UNREFLECTED_CHANGE,
                severity=Severity.warning,
                path=node.path,
                doc_id=node.id,
                message=(
                    f"source file(s) claimed by this doc changed in the diff but the doc did not: "
                    f"{shown}"
                ),
                suggestion=(
                    "update the doc in the same change, or run "
                    "`irminsul context <changed-file>` to see what it claims"
                ),
                subject=doc_path,
                # Not the doc: a later edit to it either answers the warning or is cosmetic.
                about=tuple(files),
            )
        )
    return out
