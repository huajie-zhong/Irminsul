"""Which base `check --diff` is given, and what each one can still see.

The gate is only as good as the revision it compares against. `--diff HEAD` on a branch
compares the change with itself, because HEAD already holds the commits being judged —
so a weakening committed before the run passes. CI passes the integration branch instead,
and the CLI takes the merge base of that ref and HEAD.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from .conftest import check_codes, commit_all, git, write
from .test_diff_integrity import _CONFIG, _repo

runner = CliRunner()

_ENABLED = '[checks]\nenabled = ["frontmatter", "links"]\n'


def _base_repo(root: Path) -> str:
    _repo(root)
    write(root, "irminsul.toml", _CONFIG + _ENABLED)
    return commit_all(root, "base")


def _weaken(root: Path) -> None:
    write(root, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')


def _branch(root: Path, name: str) -> None:
    git(root, "checkout", "-q", "-b", name)


def test_an_uncommitted_weakening_is_caught_against_head(tmp_path: Path) -> None:
    """The working tree is not in HEAD, so HEAD is a real baseline for it."""
    base = _base_repo(tmp_path)
    _weaken(tmp_path)

    assert "diff-integrity/check-disabled" in check_codes(tmp_path, "--diff", base)
    assert "diff-integrity/check-disabled" in check_codes(tmp_path, "--diff", "HEAD")


def test_a_committed_weakening_is_invisible_to_head(tmp_path: Path) -> None:
    """The failure this exists to pin: one `git commit` and the same change passes."""
    base = _base_repo(tmp_path)
    _branch(tmp_path, "feature")
    _weaken(tmp_path)
    commit_all(tmp_path, "turn the check off")

    assert "diff-integrity/check-disabled" not in check_codes(tmp_path, "--diff", "HEAD")
    assert "diff-integrity/check-disabled" in check_codes(tmp_path, "--diff", base)


def test_a_weakening_several_commits_back_is_still_caught(tmp_path: Path) -> None:
    base = _base_repo(tmp_path)
    _branch(tmp_path, "feature")
    _weaken(tmp_path)
    commit_all(tmp_path, "turn the check off")
    write(tmp_path, "docs/components/a.md", "---\nid: a\ntitle: A\nstatus: stable\n---\n\n# A\n")
    commit_all(tmp_path, "add a doc")
    write(tmp_path, "docs/components/b.md", "---\nid: b\ntitle: B\nstatus: stable\n---\n\n# B\n")
    commit_all(tmp_path, "add another")

    assert "diff-integrity/check-disabled" not in check_codes(tmp_path, "--diff", "HEAD")
    assert "diff-integrity/check-disabled" in check_codes(tmp_path, "--diff", base)


def test_the_comparison_is_the_merge_base_not_the_branch_tip(tmp_path: Path) -> None:
    """The base branch moving on is not this change's doing. Comparing with its tip would
    report whatever landed there meanwhile as something this branch did."""
    base = _base_repo(tmp_path)
    default = git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")

    _branch(tmp_path, "feature")
    write(tmp_path, "docs/components/a.md", "---\nid: a\ntitle: A\nstatus: stable\n---\n\n# A\n")
    commit_all(tmp_path, "work on the branch")

    git(tmp_path, "checkout", "-q", default)
    _weaken(tmp_path)
    commit_all(tmp_path, "someone else turns the check off on the base branch")
    git(tmp_path, "checkout", "-q", "feature")

    # Against the base branch's tip the branch looks like it re-enabled a check, and the
    # tip's own weakening is outside the range. Against the merge base — which is `base` —
    # the branch is judged for what it did, which is nothing to the config.
    assert check_codes(tmp_path, "--diff", default) == check_codes(tmp_path, "--diff", base)
    assert "diff-integrity/check-disabled" not in check_codes(tmp_path, "--diff", base)


def test_a_branch_that_weakens_is_caught_from_the_merge_base(tmp_path: Path) -> None:
    base = _base_repo(tmp_path)
    default = git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")
    _branch(tmp_path, "feature")
    _weaken(tmp_path)
    commit_all(tmp_path, "turn the check off")

    git(tmp_path, "checkout", "-q", default)
    write(tmp_path, "docs/components/z.md", "---\nid: z\ntitle: Z\nstatus: stable\n---\n\n# Z\n")
    commit_all(tmp_path, "unrelated work lands on the base branch")
    git(tmp_path, "checkout", "-q", "feature")

    assert "diff-integrity/check-disabled" in check_codes(tmp_path, "--diff", default)
    assert "diff-integrity/check-disabled" in check_codes(tmp_path, "--diff", base)


def test_the_workflow_passes_the_event_base_not_head() -> None:
    """The guidance and the workflow have to agree, and the workflow is the one that
    runs. Read from the repository's own CI rather than restated here."""
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8")

    assert 'irminsul check --diff "origin/${BASE_REF#refs/heads/}"' in text
    assert "github.base_ref" in text
    assert "github.event.merge_group.base_ref" in text
    assert "merge_group:" in text
    assert "--diff HEAD" not in text
