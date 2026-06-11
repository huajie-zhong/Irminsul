"""Co-change enforcement — docs ship in the same change as the code they claim.

Not a registered graph check: it needs the changed-file set from
`git diff <base>...HEAD`, which only the CLI's `--diff <base>` flag supplies.
Ownership is resolved through the exact `describes` glob logic the uniqueness
check uses (`resolve_claims` / `most_specific_claims`), so "who owns this
file?" has one answer everywhere. Findings are warnings and flow through the
normal printing/JSON/summary pipeline, so `--strict` promotes them to errors
like any other soft signal.
"""

from __future__ import annotations

from typing import Final

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.checks.uniqueness import most_specific_claims, resolve_claims
from irminsul.docgraph import DocGraph, DocNode

CHECK_NAME: Final = "co-change"


def run_co_change(graph: DocGraph, changed: frozenset[str]) -> list[Finding]:
    """Warn for each owning doc whose claimed sources changed without it.

    `changed` is the repo-relative POSIX path set from `git diff --name-only`.
    A changed source file is "unreflected" when none of its most-specific
    owning docs appear in the changed set; findings are grouped per owning
    doc, listing every unreflected file it claims.
    """
    if graph.config is None or graph.repo_root is None:
        return []

    source_files, _missing = walk_source_files(graph.repo_root, graph.config.paths.source_roots)
    claims_by_file = resolve_claims(graph, source_files)

    unreflected_by_doc: dict[str, tuple[DocNode, list[str]]] = {}
    for source_file in sorted(changed):
        claims = claims_by_file.get(source_file)
        if not claims:
            continue  # unclaimed file — nothing owns it, nothing to enforce
        owners = {node.path.as_posix(): node for node, _, _ in most_specific_claims(claims)}
        if any(doc_path in changed for doc_path in owners):
            continue  # an owning doc shipped in the same change
        for doc_path, node in owners.items():
            _, files = unreflected_by_doc.setdefault(doc_path, (node, []))
            files.append(source_file)

    out: list[Finding] = []
    for doc_path in sorted(unreflected_by_doc):
        node, files = unreflected_by_doc[doc_path]
        listed = ", ".join(files)
        out.append(
            Finding(
                check=CHECK_NAME,
                severity=Severity.warning,
                path=node.path,
                doc_id=node.id,
                message=(
                    f"source file(s) claimed by this doc changed in the diff "
                    f"but the doc did not: {listed}"
                ),
                suggestion=(
                    "update the doc in the same change, or run "
                    "`irminsul context <changed-file>` to see what it claims"
                ),
            )
        )
    return out
