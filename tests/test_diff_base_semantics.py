"""Which base `check --diff` is given, and what each one can still see.

The gate is only as good as the revision it compares against. `--diff HEAD` on a branch
compares the change with itself, because HEAD already holds the commits being judged —
so a weakening committed before the run passes. CI passes the integration branch instead,
and the CLI takes the merge base of that ref and HEAD.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .test_diff_integrity import _CONFIG, _commit, _git, _repo, _write

runner = CliRunner()

_ENABLED = '[checks]\nenabled = ["frontmatter", "links"]\n'


def _base_repo(root: Path) -> str:
    _repo(root)
    _write(root, "irminsul.toml", _CONFIG + _ENABLED)
    return _commit(root, "base")


def _weaken(root: Path) -> None:
    _write(root, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')


def _codes(root: Path, base: str) -> list[str]:
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return sorted(f["code"] for f in json.loads(result.output)["findings"])


def _branch(root: Path, name: str) -> None:
    _git(root, "checkout", "-q", "-b", name)


def test_an_uncommitted_weakening_is_caught_against_head(tmp_path: Path) -> None:
    """The working tree is not in HEAD, so HEAD is a real baseline for it."""
    base = _base_repo(tmp_path)
    _weaken(tmp_path)

    assert "diff-integrity/check-disabled" in _codes(tmp_path, base)
    assert "diff-integrity/check-disabled" in _codes(tmp_path, "HEAD")


def test_a_committed_weakening_is_invisible_to_head(tmp_path: Path) -> None:
    """The failure this exists to pin: one `git commit` and the same change passes."""
    base = _base_repo(tmp_path)
    _branch(tmp_path, "feature")
    _weaken(tmp_path)
    _commit(tmp_path, "turn the check off")

    assert "diff-integrity/check-disabled" not in _codes(tmp_path, "HEAD")
    assert "diff-integrity/check-disabled" in _codes(tmp_path, base)


def test_a_weakening_several_commits_back_is_still_caught(tmp_path: Path) -> None:
    base = _base_repo(tmp_path)
    _branch(tmp_path, "feature")
    _weaken(tmp_path)
    _commit(tmp_path, "turn the check off")
    _write(tmp_path, "docs/components/a.md", "---\nid: a\ntitle: A\nstatus: stable\n---\n\n# A\n")
    _commit(tmp_path, "add a doc")
    _write(tmp_path, "docs/components/b.md", "---\nid: b\ntitle: B\nstatus: stable\n---\n\n# B\n")
    _commit(tmp_path, "add another")

    assert "diff-integrity/check-disabled" not in _codes(tmp_path, "HEAD")
    assert "diff-integrity/check-disabled" in _codes(tmp_path, base)


def test_the_comparison_is_the_merge_base_not_the_branch_tip(tmp_path: Path) -> None:
    """The base branch moving on is not this change's doing. Comparing with its tip would
    report whatever landed there meanwhile as something this branch did."""
    base = _base_repo(tmp_path)
    default = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")

    _branch(tmp_path, "feature")
    _write(tmp_path, "docs/components/a.md", "---\nid: a\ntitle: A\nstatus: stable\n---\n\n# A\n")
    _commit(tmp_path, "work on the branch")

    _git(tmp_path, "checkout", "-q", default)
    _weaken(tmp_path)
    _commit(tmp_path, "someone else turns the check off on the base branch")
    _git(tmp_path, "checkout", "-q", "feature")

    # Against the base branch's tip the branch looks like it re-enabled a check, and the
    # tip's own weakening is outside the range. Against the merge base — which is `base` —
    # the branch is judged for what it did, which is nothing to the config.
    assert _codes(tmp_path, default) == _codes(tmp_path, base)
    assert "diff-integrity/check-disabled" not in _codes(tmp_path, base)


def test_a_branch_that_weakens_is_caught_from_the_merge_base(tmp_path: Path) -> None:
    base = _base_repo(tmp_path)
    default = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD")
    _branch(tmp_path, "feature")
    _weaken(tmp_path)
    _commit(tmp_path, "turn the check off")

    _git(tmp_path, "checkout", "-q", default)
    _write(tmp_path, "docs/components/z.md", "---\nid: z\ntitle: Z\nstatus: stable\n---\n\n# Z\n")
    _commit(tmp_path, "unrelated work lands on the base branch")
    _git(tmp_path, "checkout", "-q", "feature")

    assert "diff-integrity/check-disabled" in _codes(tmp_path, default)
    assert "diff-integrity/check-disabled" in _codes(tmp_path, base)


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
