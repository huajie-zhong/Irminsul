"""History depth — the enabled checks must be able to read the history they need.

A pass, not a check: like `diff-integrity`, it judges the run rather than the graph, so
no `checks.enabled` list can leave it out. Several checks answer their question from
`git log`; given a checkout with no history they find nothing and report nothing, which is
indistinguishable from a clean tree. `actions/checkout` clones to depth 1 by default, so
that silence is the common case rather than the rare one.

It reports only when an enabled check reads history, which is what lets the change
lifecycle gates block on its findings: a run asking no historical question has nothing
here to fail on.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

from irminsul.checks import flagged
from irminsul.checks.base import CheckFlag, Finding, FindingClass, Severity
from irminsul.git.mtime import git_root_for, history_state

if TYPE_CHECKING:
    from collections.abc import Collection

    from irminsul.docgraph import DocGraph
    from irminsul.git.reader import GitReader

CHECK_NAME: Final = "history-depth"
CODE_SHALLOW_CLONE: Final = "history-depth/shallow-clone"
CODE_NO_HISTORY: Final = "history-depth/no-history"


class HistoryDepthPass:
    """The checkout must hold enough git history for the checks that read it."""

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_SHALLOW_CLONE: (
            "The repository is a shallow clone, so the checks that read commit history "
            "cannot see it and report nothing. Fetch the full history — in GitHub "
            "Actions, `fetch-depth: 0` on actions/checkout."
        ),
        CODE_NO_HISTORY: (
            "There is no git repository here, so the checks that read commit history "
            "have nothing to read. Expected while a scaffold is not committed yet; in "
            "CI it means the tree was copied rather than cloned."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_SHALLOW_CLONE: FindingClass.certain,
        CODE_NO_HISTORY: FindingClass.hint,
    }

    def run(self, graph: DocGraph, selected: Collection[str]) -> list[Finding]:
        """Findings for a checkout too shallow to answer the checks that are running.

        `selected` is what the run actually resolved, not `config.checks.enabled`: `--only`
        runs a check regardless of the config, and reading the config instead would leave
        this guard silent for a history-reading check the run selected that way.
        """
        repo_root = graph.repo_root
        if repo_root is None:
            return []
        reading = sorted(set(selected).intersection(flagged(CheckFlag.reads_history)))
        if not reading:
            return []
        named = ", ".join(reading)
        git = graph.git
        has_history, shallow = history_state(git, repo_root)
        if not has_history:
            # `history_state` asks about this directory exactly, because the callers that
            # read `git log` need paths relative to the root they pass. The checks named
            # here resolve a file's history by walking up instead, so a config root inside
            # a larger repository can answer them fine — and saying otherwise is false.
            #
            # Finding an enclosing repository is not enough, though: a tree copied into one,
            # or a nested repository the outer one ignores, has an ancestor with history and
            # none of its own. The question is whether any commit reaches *this* directory.
            enclosing = git_root_for(repo_root)
            if (
                enclosing is not None
                and enclosing != repo_root.resolve()
                and _has_commits_here(git, repo_root)
            ):
                has_history, shallow = history_state(git, enclosing)
        if not has_history:
            return [
                _finding(
                    CODE_NO_HISTORY,
                    Severity.warning,
                    f"no git history here, so {named} read nothing and report nothing",
                    "commit the tree, or disable the checks that read history",
                )
            ]
        if shallow:
            return [
                _finding(
                    CODE_SHALLOW_CLONE,
                    Severity.error,
                    f"shallow clone: {named} read commit history and find none of it here",
                    "check out the full history — in GitHub Actions, fetch-depth: 0",
                )
            ]
        return []


def _has_commits_here(git: GitReader, repo_root: Path) -> bool:
    """Whether the enclosing repository records any commit touching this directory."""
    return bool((git.text(repo_root, "log", "-1", "--format=%H", "--", ".") or "").strip())


def _finding(code: str, severity: Severity, message: str, suggestion: str) -> Finding:
    return Finding(
        check=CHECK_NAME,
        code=code,
        severity=severity,
        message=message,
        path=Path("."),
        suggestion=suggestion,
    )
