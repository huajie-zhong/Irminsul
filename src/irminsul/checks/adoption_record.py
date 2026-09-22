"""Whether the adoption record can be trusted to except anything.

This pass is not in `REGISTRY`, and that is the point. The record grants exceptions to
`uniqueness` and `test-ownership`, and `checks.enabled` is a list a repository writes — so
a project running `test-ownership` alone used to honour a record nothing had validated:
malformed JSON fell back to the progressive rule, and a cross-repository boundary nobody
could read was accepted in silence. Reporting lived in `uniqueness` on the reasoning that
two checks saying one thing is noise, which is true, and irrelevant when `uniqueness` is
not among the checks selected.

So validity is asked here, the way `history-depth` asks whether the checkout can answer
the checks that were selected: once, outside the list, reported once. The ownership checks
consume the verified set and say nothing about the record.

It reports nothing when no ownership rule is running. A record that excepts a finding
nobody asked for is not wrong, it is merely unused.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

from irminsul.checks.base import Finding, FindingClass, Severity

if TYPE_CHECKING:
    from collections.abc import Iterable

    from irminsul.adoption import DebtProblem
    from irminsul.docgraph import DocGraph

CHECK_NAME: Final = "adoption-record"
CODE_UNREADABLE: Final = "adoption-record/unreadable"
CODE_SOURCE_UNVERIFIABLE: Final = "adoption-record/source-unverifiable"
CODE_NOT_AT_SOURCE_REVISION: Final = "adoption-record/debt-not-at-source-revision"

#: The rules the record grants exceptions to. Nothing here fires unless one is selected.
OWNERSHIP_CHECKS: Final = frozenset({"uniqueness", "test-ownership"})


class AdoptionRecordCheck:
    """Gives the adoption-record pass a `name` and `explanations` for `irminsul explain`."""

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNREADABLE: (
            "The adoption record does not load, so which files were already unowned when this "
            "repository adopted Irminsul cannot be read. Nothing is excepted while that is "
            "true, and nothing is assumed either. Restore the file from git, or delete it and "
            "record the debt as it stands with `check --init-adoption`."
        ),
        CODE_SOURCE_UNVERIFIABLE: (
            "Entries in the adoption record come from a root in a separate git repository, and "
            "nothing establishes that those files were already there when this repository "
            "adopted. This repository's history cannot answer for another one, so the record "
            "has to pin the source revision, and the repository has to be present at it. The "
            "entries go on excepting their files while this is unresolved — calling them new "
            "would assert the opposite of what could not be checked — and this finding fails "
            "the run instead."
        ),
        CODE_NOT_AT_SOURCE_REVISION: (
            "The adoption record calls a file pre-existing debt, but the source repository did "
            "not hold it at the revision the record adopted, so the file is new. Give it an "
            "owning doc; the record cannot except a file that was not there at the boundary."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNREADABLE: FindingClass.certain,
        CODE_SOURCE_UNVERIFIABLE: FindingClass.certain,
        CODE_NOT_AT_SOURCE_REVISION: FindingClass.certain,
    }
    #: The adoption record *is* a suppression marker: it excepts files from the ownership
    #: finding. Every code here says that suppression cannot be trusted — unreadable, or
    #: covering a file the boundary does not show was there. A baseline that could hide one
    #: would leave the exceptions in force while the only thing checking them went quiet,
    #: which is the shape `baselinable` already refuses for every other suppression audit.
    audits_suppression: ClassVar[frozenset[str]] = frozenset(
        {CODE_UNREADABLE, CODE_SOURCE_UNVERIFIABLE, CODE_NOT_AT_SOURCE_REVISION}
    )

    def run(self, graph: DocGraph) -> list[Finding]:
        raise NotImplementedError(
            "adoption-record needs the selected check names; call run_adoption_record(graph, ...)"
        )


def run_adoption_record(graph: DocGraph, selected: Iterable[str]) -> list[Finding]:
    """Findings about the record itself, or none when no ownership rule consults it."""
    from irminsul.adoption import AdoptionError, load_record, record_path, verified_debt

    if graph.config is None or graph.repo_root is None:
        return []
    if not (OWNERSHIP_CHECKS & set(selected)):
        return []
    path = record_path(graph.repo_root, graph.config)
    if not path.is_file():
        return []
    try:
        record = load_record(path)
    except AdoptionError as exc:
        return [
            Finding(
                check=CHECK_NAME,
                code=CODE_UNREADABLE,
                severity=Severity.error,
                path=Path(graph.config.paths.adoption),
                message=f"the adoption record does not load, so ownership debt is unknown: {exc}",
                suggestion=(
                    "restore the file from git, or delete it and run "
                    "`irminsul check --init-adoption` to record the debt as it stands"
                ),
                data={"problem": "adoption-record-unreadable"},
            )
        ]
    _, problems = verified_debt(graph.repo_root, graph.config, record, graph.source_map)
    return [_finding(graph, problem) for problem in problems]


def _finding(graph: DocGraph, problem: DebtProblem) -> Finding:
    """One `DebtProblem` as the finding that says so."""
    assert graph.config is not None
    if problem.kind == "not_historical":
        return Finding(
            check=CHECK_NAME,
            code=CODE_NOT_AT_SOURCE_REVISION,
            severity=Severity.error,
            path=Path(str(problem.display)),
            message=problem.detail,
            suggestion=(
                "give it an owning doc — add it to a doc's `describes:`, or write one with "
                "`irminsul new component`"
            ),
            data={"problem": "adoption-debt-not-at-source-revision", "path": str(problem.display)},
        )
    return Finding(
        check=CHECK_NAME,
        code=CODE_SOURCE_UNVERIFIABLE,
        severity=Severity.error,
        # A problem about one entry is reported on that entry's file, and one about a whole
        # boundary on the record. Reporting every unverifiable thing on the record read as
        # one broken file when the broken thing was one line in it.
        path=Path(problem.display) if problem.display else Path(graph.config.paths.adoption),
        message=problem.detail,
        suggestion=problem.remedy,
        data={"problem": "adoption-source-unverifiable", "root": problem.root},
    )


__all__ = [
    "CHECK_NAME",
    "CODE_NOT_AT_SOURCE_REVISION",
    "CODE_SOURCE_UNVERIFIABLE",
    "CODE_UNREADABLE",
    "AdoptionRecordCheck",
    "run_adoption_record",
]
