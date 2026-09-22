"""`check --delta`: report only findings introduced by the working tree.

Mechanism: check out the base rev into a scratch `git worktree`, run the same
configured checks there, and keep only worktree findings whose fingerprint
(check, path, message — see `irminsul.baseline`) does not appear in the base
run. Reuses baseline's fingerprint so "new" means the same thing under
`--delta` as it does under the baseline ratchet.

The scratch worktree lives under the system temp dir, never inside the
target repo, and is removed unconditionally. `git worktree add --detach`
never touches the caller's working tree or index.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from irminsul.baseline import finding_fingerprint
from irminsul.checks.base import Finding
from irminsul.git.mtime import git_root_for

if TYPE_CHECKING:
    from irminsul.config import IrminsulConfig


class DeltaError(Exception):
    """Raised when `--delta` cannot produce a base-rev comparison."""


@dataclass(frozen=True)
class DeltaResult:
    new: list[Finding]
    pre_existing: int


#: The two ways a finding message names a position in a file: `at line 9`, and the
#: `path.ext:9` form. Only these are blanked. Blanking every digit instead concealed the
#: figure that *is* the violation — `widened from 30 to 100` and `widened from 30 to 3650`
#: both flattened to `widened from # to #`, so a worse weakening of the gate read as the
#: one already there.
_LOCATION = re.compile(r"(\bline )\d+|(\.[A-Za-z0-9]{1,8}:)\d+")


def _blank_locations(message: str) -> str:
    return _LOCATION.sub(lambda m: (m.group(1) or m.group(2)) + "#", message)


def _kind(finding: Finding) -> tuple[str, str, str, str]:
    """This finding's identity with the positions in its message blanked.

    Positions only. A message differing in a *word* or in any other *figure* describes a
    different problem — `missing 'audience'` and `missing 'status'` are two facts about one
    file, and `30` against `3650` is the whole content of a threshold finding — so merging
    either would hide a real regression behind a fix. A message differing only in where it
    points is the same violation seen from a file that shifted under it.
    """
    return (
        finding.check,
        finding.code,
        finding.path.as_posix() if finding.path else "",
        _blank_locations(finding.message),
    )


def compute_delta(worktree_findings: list[Finding], base_findings: list[Finding]) -> DeltaResult:
    """Split worktree findings into new (not in the base run) and pre-existing.

    All severities are compared the same way — unlike the baseline ratchet, info findings
    are not special-cased, since delta's job is "did this diff cause it", not "is it debt
    worth tracking".

    Matched in two passes, because a fingerprint is `(check, path, message)` and some
    messages carry a line number: `duplicate-block` says "repeats the one at line 9", so
    inserting an unrelated paragraph above the pair rewrote the message and the untouched
    violation came back as newly introduced. The second pass pairs what is left by the
    same message with its figures blanked, counting occurrences — so a violation that only
    moved is recognised, a second one of the same shape in the same file is still new, and
    a message differing in any word at all is left alone.
    """
    unmatched_fingerprints = Counter(finding_fingerprint(f) for f in base_findings)
    unmatched_kinds = Counter(_kind(f) for f in base_findings)

    pre_existing = 0
    undecided: list[Finding] = []
    for finding in worktree_findings:
        fingerprint = finding_fingerprint(finding)
        if unmatched_fingerprints[fingerprint] > 0:
            unmatched_fingerprints[fingerprint] -= 1
            unmatched_kinds[_kind(finding)] -= 1
            pre_existing += 1
        else:
            undecided.append(finding)

    new: list[Finding] = []
    for finding in undecided:
        kind = _kind(finding)
        if unmatched_kinds[kind] > 0:
            unmatched_kinds[kind] -= 1
            pre_existing += 1
        else:
            new.append(finding)
    return DeltaResult(new=new, pre_existing=pre_existing)


def cross_repo_trees(repo_root: Path, config: IrminsulConfig) -> list[str]:
    """Configured trees owned by a git repository other than `repo_root`'s.

    `git worktree add` checks out tracked files only, so a tree that belongs to
    another repository is simply absent from the base checkout. In the siblings
    layout that is the code repo `source_roots` reach through `../`. Checked per
    configured root rather than by scanning the tree, so an unrelated vendored
    checkout never trips it.

    `docs_root` is inspected too, even though no supported layout puts it in
    another repository. This is not layout policing: `--delta` is answering
    "which findings are new", and a `docs_root` carrying its own `.git` — an
    ordinary git submodule is enough — is absent from the base worktree exactly
    the way a sibling code repo is, so every pre-existing finding in the docs
    tree comes back as new. A refusal is recoverable; a confidently inverted
    answer is not, and telling the two shapes apart costs one element in this
    loop.

    A configured root that is missing on disk is skipped — the source walk
    already reports it, and its absence says nothing about the layout.
    """
    own_root = git_root_for(repo_root)
    if own_root is None:
        return []
    own_resolved = own_root.resolve()
    outside: list[str] = []
    for rel in (config.paths.docs_root, *config.paths.source_roots):
        tree = (repo_root / rel).resolve()
        if not tree.is_dir():
            continue
        owner = git_root_for(tree)
        if owner is None or owner.resolve() != own_resolved:
            outside.append(rel)
    return outside


def base_is_the_working_tree(repo_root: Path, config: IrminsulConfig, base_rev: str) -> bool:
    """Whether comparing against `base_rev` would compare the tree with itself.

    Asking the trees rather than the flags: `--delta-base HEAD`, and the sha `HEAD`
    resolves to, name exactly the state the default does, so keying the refusal to
    `--delta-base` being absent left the same vacuous run one spelling away.
    """
    from irminsul.git.mtime import _git_text

    base_tree = _git_text(repo_root, "rev-parse", f"{base_rev}^{{tree}}")
    head_tree = _git_text(repo_root, "rev-parse", "HEAD^{tree}")
    if base_tree is None or base_tree.strip() != (head_tree or "").strip():
        return False
    return not _changes_the_checks_can_see(repo_root, config)


def _changes_the_checks_can_see(repo_root: Path, config: IrminsulConfig) -> bool:
    """Whether the working tree differs from HEAD anywhere a check would look.

    Not "is the tree dirty": `working_tree_changed_paths` lists untracked files too, so
    one scratch file beside the repository turned the refusal below into a green run
    that suppressed every finding in the tree. A file no configured walk reads cannot
    change what `--delta` would compare.
    """
    from irminsul.config import CONFIG_FILENAME, docs_root_prefix
    from irminsul.git.changes import GitChangesError, working_tree_changed_paths

    watched = {
        docs_root_prefix(config),
        CONFIG_FILENAME,
        ".github/workflows",
        *config.paths.source_roots,
        *config.paths.extra_docs,
    }
    try:
        changed = working_tree_changed_paths(repo_root)
    except GitChangesError:
        return True  # let the delta machinery report the git problem itself
    return any(
        path == watched_path
        or path.startswith(f"{watched_path.rstrip('/')}/")
        or watched_path in (".", "")
        for path in changed
        for watched_path in watched
    )


def verify_single_repo_topology(repo_root: Path, config: IrminsulConfig) -> None:
    """Raise `DeltaError` when `--delta` would silently compare against a tree
    the base checkout cannot contain.

    Of the two supported layouts this guards exactly one: `siblings`, where the
    code repo is a separate git repository that `git worktree add` cannot
    reproduce. It also catches a configured tree that answers to another
    repository for reasons no layout chose — a docs submodule, say. Without the
    guard the base run finds nothing under those roots, so every finding over
    them survives as "new" — the exact inversion of what `--delta` promises,
    delivered with a nonzero exit and no warning.

    Teaching `--delta` to compare across the sibling boundary is open work; the
    seam is here, and it is the only place the refusal is decided.
    """
    outside = cross_repo_trees(repo_root, config)
    if not outside:
        return
    roots = ", ".join(repr(r) for r in outside)
    raise DeltaError(
        f"--delta cannot compare across a repository boundary yet: {roots} "
        f"belong(s) to a different git repository than {repo_root}. "
        "`git worktree add` checks out tracked files only, so the base "
        "checkout would omit them and every finding over them would be "
        "reported as new. Re-run `check` without --delta, and use mtime-drift "
        "as the cross-repository signal."
    )


@contextmanager
def pristine_checkout(repo_root: Path, rev: str) -> Generator[Path, None, None]:
    """Check out `rev` into a scratch `git worktree` and yield its root.

    `repo_root` must itself be a git worktree root (mirrors `--diff`'s
    `_open_repo` contract: no parent-directory search). The scratch worktree
    is removed in a `finally` block even if the caller raises.
    """
    try:
        repo = Repo(repo_root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError) as e:
        raise DeltaError(
            f"no git repository with commit history found at {repo_root}; "
            "--delta needs one to check out --delta-base"
        ) from e

    # Resolve the temp root: the system temp dir is a symlink on macOS
    # (/var -> /private/var) and can be an 8.3 short name on Windows, while the
    # doc walk yields fully resolved paths. An unresolved root here makes
    # `parse_doc`'s `relative_to(repo_root)` raise for every doc it finds.
    scratch_parent = Path(tempfile.mkdtemp(prefix="irminsul-delta-")).resolve()
    scratch_dir = scratch_parent / "base"
    try:
        try:
            repo.git.worktree("add", "--detach", str(scratch_dir), rev)
        except GitCommandError as e:
            raise DeltaError(f"could not check out --delta-base {rev!r}: {e}") from e
        finally:
            # Release the handle before the yield rather than after. The caller
            # runs a full check pass in there — seconds, not milliseconds — and
            # `repo` goes unused for all of it, while GitPython keeps a
            # persistent git process alive behind it. `_remove_worktree` retries
            # precisely because Windows can still be holding the checkout open.
            repo.close()
        try:
            yield scratch_dir
        finally:
            cleanup_repo = Repo(repo_root, search_parent_directories=False)
            try:
                _remove_worktree(cleanup_repo, scratch_dir)
            finally:
                cleanup_repo.close()
    finally:
        shutil.rmtree(scratch_parent, ignore_errors=True)


def _remove_worktree(repo: Repo, scratch_dir: Path) -> None:
    """Best-effort, retrying removal. Windows can hold file-lock handles open
    briefly after a checkout, so a plain `worktree remove` can transiently
    fail; retry with backoff, then fall back to `worktree prune` so the main
    repo's `.git/worktrees` metadata never leaks a stale entry."""
    attempts = 5
    for attempt in range(attempts):
        try:
            repo.git.worktree("remove", "--force", str(scratch_dir))
            return
        except GitCommandError:
            if attempt == attempts - 1:
                break
            time.sleep(0.2 * (attempt + 1))
    with suppress(GitCommandError):
        repo.git.worktree("prune")
