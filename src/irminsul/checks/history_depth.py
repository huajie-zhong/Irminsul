"""History depth — the enabled checks must be able to read the history they need.

Not a registered graph check: like `diff-integrity`, it judges the run rather than the
graph, so the CLI calls `run_history_depth` directly and no `checks.enabled` list can
leave it out. Several checks answer their question from `git log`; given a checkout with
no history they find nothing and report nothing, which is indistinguishable from a clean
tree. `actions/checkout` clones to depth 1 by default, so that silence is the common
case rather than the rare one.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Final

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.git.mtime import _git_text, git_root_for, history_state

CHECK_NAME: Final = "history-depth"
CODE_SHALLOW_CLONE: Final = "history-depth/shallow-clone"
CODE_NO_HISTORY: Final = "history-depth/no-history"
CODE_DIFF_UNAVAILABLE: Final = "history-depth/diff-unavailable"

#: Checks that answer their question from commit history, so a truncated history
#: silently turns them into no-ops.
HISTORY_READING_CHECKS: Final = frozenset(
    {
        "mtime-drift",
        "stale-reaper",
        "claim-provenance",
        "rfc-follow-through",
        "change-binding",
    }
)


class HistoryDepthCheck:
    """Gives the history-depth pass a `name` and `explanations` for `irminsul explain`."""

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
        CODE_DIFF_UNAVAILABLE: (
            "`--base-ref`/`--head-ref` could not resolve their range, so the diff-aware "
            "passes — co-change, and the sealing of implemented records — did not run. "
            "That is by design for these two flags, which degrade rather than fail, so "
            "the run is reported as having covered less than it looks. Fetch the base ref "
            "(in GitHub Actions, `fetch-depth: 0`), or use `--diff`, which exits instead."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_SHALLOW_CLONE: FindingClass.certain,
        CODE_NO_HISTORY: FindingClass.hint,
        CODE_DIFF_UNAVAILABLE: FindingClass.hint,
    }

    def run(self, graph: object) -> list[Finding]:  # pragma: no cover - not registered
        return []


def _has_commits_here(repo_root: Path) -> bool:
    """Whether the enclosing repository records any commit touching this directory."""
    return bool((_git_text(repo_root, "log", "-1", "--format=%H", "--", ".") or "").strip())


def run_history_depth(repo_root: Path, enabled: Iterable[str]) -> list[Finding]:
    """Findings for a checkout too shallow to answer the checks that are running.

    `enabled` is what the run actually resolved, not `config.checks.enabled`:
    `--profile all-available` runs the whole registry regardless of the config, and
    reading the config instead made this guard silent for the profile running the most
    history-reading checks.
    """
    reading = sorted(HISTORY_READING_CHECKS.intersection(enabled))
    if not reading:
        return []
    named = ", ".join(reading)
    has_history, shallow = history_state(repo_root)
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
        if enclosing is not None and enclosing != repo_root and _has_commits_here(repo_root):
            has_history, shallow = history_state(enclosing)
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


def diff_unavailable(reason: str) -> Finding:
    """The finding for a `--base-ref` range that would not resolve.

    Printed as a warning on stderr alone, this degradation was invisible in the report,
    in JSON, and in CI annotations: a run that skipped the sealing passes looked exactly
    like one that passed them.
    """
    return _finding(
        CODE_DIFF_UNAVAILABLE,
        Severity.warning,
        f"{reason}; the diff-aware passes did not run",
        "fetch the base ref — in GitHub Actions, fetch-depth: 0 — or use --diff",
    )


def _finding(code: str, severity: Severity, message: str, suggestion: str) -> Finding:
    category = code.split("/", 1)[1]
    return Finding(
        check=CHECK_NAME,
        code=code,
        category=category,
        severity=severity,
        message=message,
        path=Path("."),
        suggestion=suggestion,
        data={"problem": category},
    )
