"""`check --diff` judges the working tree, so one run before committing shows what the commit
will trigger, and `--committed-only` leaves that work out.

Every test builds a real repository on a feature branch off `main`, with fixed commit dates.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import pytest

from irminsul import cli

from .conftest import (
    check_codes,
    check_findings,
    commit_all,
    config_toml,
    git,
    git_init,
    invoke,
    write,
    write_config,
)
from .test_checks_new_dependency import ALPHA, _doc
from .test_cli_cochange import _DOC_BODY, _TOML
from .test_diff_integrity import _ADR, _repo

_UNREFLECTED = "co-change/unreflected-change"
_ACKNOWLEDGED = "co-change/acknowledged"
_TRAILER = 'Irminsul-Reviewed: co-change docs/components/alpha.md reason="re-read, still right"'


def _at(day: int) -> _dt.datetime:
    return _dt.datetime(2026, 1, day, 12, tzinfo=_dt.UTC)


def _feature(tmp_path: Path) -> tuple[Path, str]:
    """A repository whose `alpha` doc claims `app/alpha.py` and `app/beta.py`, on a feature
    branch with nothing committed yet; returns the root and the base commit."""
    root = tmp_path / "r"
    git_init(root, branch="main")
    write(root, "app/alpha.py", "a = 1\n")
    write(root, "app/beta.py", "b = 1\n")
    write(root, "docs/components/alpha.md", _DOC_BODY)
    write(root, "irminsul.toml", _TOML)
    base = commit_all(root, "seed", when=_at(1))
    git(root, "checkout", "-q", "-b", "feature")
    return root, base


def _one(findings: list[dict[str, Any]], code: str) -> dict[str, Any]:
    [found] = [f for f in findings if f["code"] == code]
    return found


@pytest.mark.parametrize("staged", [False, True])
def test_uncommitted_edit_to_claimed_code_warns_its_owner(tmp_path: Path, staged: bool) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")
    if staged:
        git(root, "add", "app/alpha.py")

    found = _one(check_findings(root, "--diff", base), _UNREFLECTED)

    assert found["path"] == "docs/components/alpha.md"
    assert "app/alpha.py (uncommitted)" in found["message"]
    assert "in the message of the commit that carries app/alpha.py" in found["suggestion"]


def test_an_unstaged_deletion_of_claimed_code_warns_its_owner(tmp_path: Path) -> None:
    root, base = _feature(tmp_path)
    (root / "app" / "alpha.py").unlink()

    found = _one(check_findings(root, "--diff", base), _UNREFLECTED)

    assert "app/alpha.py (uncommitted)" in found["message"]


def test_an_uncommitted_edit_to_the_owner_ships_with_the_code(tmp_path: Path) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")
    assert _UNREFLECTED in check_codes(root, "--diff", base)

    write(root, "docs/components/alpha.md", _DOC_BODY + "\nNow `a` is 2.\n")

    assert _UNREFLECTED not in check_codes(root, "--diff", base)


def test_committed_code_is_not_marked_uncommitted(tmp_path: Path) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")
    commit_all(root, "alpha", when=_at(2))
    write(root, "app/beta.py", "b = 2\n")

    found = _one(check_findings(root, "--diff", base), _UNREFLECTED)

    assert "app/alpha.py, app/beta.py (uncommitted)" in found["message"]


def test_a_whitespace_only_edit_to_the_owner_does_not_ship_with_dirty_code(
    tmp_path: Path,
) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")
    write(root, "docs/components/alpha.md", _DOC_BODY + "\n\n")

    assert _UNREFLECTED in check_codes(root, "--diff", base)


def test_a_commit_carrying_the_trailer_acknowledges_what_the_tree_warned_about(
    tmp_path: Path,
) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")
    assert _UNREFLECTED in check_codes(root, "--diff", base)

    commit_all(root, f"change alpha\n\n{_TRAILER}", when=_at(2))

    codes = check_codes(root, "--diff", base)
    assert _ACKNOWLEDGED in codes
    assert _UNREFLECTED not in codes


def test_a_trailer_does_not_cover_a_later_uncommitted_edit(tmp_path: Path) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")
    commit_all(root, f"change alpha\n\n{_TRAILER}", when=_at(2))
    assert _ACKNOWLEDGED in check_codes(root, "--diff", base)

    write(root, "app/alpha.py", "a = 3\n")

    findings = check_findings(root, "--diff", base)
    found = _one(findings, _UNREFLECTED)
    assert "that trailer does not count" in found["suggestion"]
    assert "predates the change to app/alpha.py (uncommitted)" in found["suggestion"]
    assert _ACKNOWLEDGED not in [f["code"] for f in findings]


def test_committed_only_leaves_uncommitted_work_out(tmp_path: Path) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")

    assert _UNREFLECTED in check_codes(root, "--diff", base)
    assert _UNREFLECTED not in check_codes(root, "--diff", base, "--committed-only")

    commit_all(root, "alpha", when=_at(2))

    assert _UNREFLECTED in check_codes(root, "--diff", base, "--committed-only")


def test_committed_only_judges_the_commits_not_what_follows_them(tmp_path: Path) -> None:
    root, base = _feature(tmp_path)
    write(root, "app/alpha.py", "a = 2\n")
    commit_all(root, f"change alpha\n\n{_TRAILER}", when=_at(2))
    write(root, "app/alpha.py", "a = 3\n")

    codes = check_codes(root, "--diff", base, "--committed-only")

    assert _ACKNOWLEDGED in codes
    assert _UNREFLECTED not in codes


def test_committed_only_reaches_the_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, base = _feature(tmp_path)
    seen: list[bool] = []
    build = cli.build_graph

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs.get("committed_only", False))
        return build(*args, **kwargs)

    monkeypatch.setattr(cli, "build_graph", spy)

    invoke(root, "check", "--diff", base)
    invoke(root, "check", "--diff", base, "--committed-only")

    assert seen == [False, True]


def test_an_uncommitted_weakening_is_judged_unless_committed_only(tmp_path: Path) -> None:
    root = _repo(tmp_path / "r")
    write(root, "irminsul.toml", config_toml(enabled=["frontmatter", "links"]))
    base = commit_all(root, "base", when=_at(1))
    git(root, "checkout", "-q", "-b", "feature")
    write(root, "irminsul.toml", config_toml(enabled=["frontmatter"]))

    assert "diff-integrity/check-disabled" in check_codes(root, "--diff", base)
    assert "diff-integrity/check-disabled" not in check_codes(
        root, "--diff", base, "--committed-only"
    )


def test_an_ignored_copy_of_a_removed_decision_does_not_keep_it_alive(tmp_path: Path) -> None:
    root = _repo(tmp_path / "r")
    write(root, "docs/decisions/0001-choice.md", _ADR)
    base = commit_all(root, "decide", when=_at(1))
    git(root, "checkout", "-q", "-b", "feature")
    git(root, "rm", "-q", "--cached", "docs/decisions/0001-choice.md")
    write(root, ".gitignore", "docs/decisions/0001-choice.md\n")

    assert (root / "docs" / "decisions" / "0001-choice.md").is_file()
    assert "diff-integrity/accepted-decision-removed" in check_codes(root, "--diff", base)


def _two_components(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "r"
    git_init(root, branch="main")
    write(root, "src/mylib/alpha.py", "def run() -> None:\n    pass\n")
    write(root, "src/mylib/shared.py", "def helper() -> None:\n    pass\n")
    write(root, "docs/components/alpha.md", _doc("alpha", "src/mylib/alpha.py"))
    write(root, "docs/components/shared.md", _doc("shared", "src/mylib/shared.py"))
    write_config(root, source_roots=["src"], enabled=[])
    return root, commit_all(root, "seed", when=_at(1))


def test_an_uncommitted_import_is_a_new_dependency(tmp_path: Path) -> None:
    root, base = _two_components(tmp_path)
    git(root, "checkout", "-q", "-b", "feature")
    write(root, "src/mylib/alpha.py", ALPHA)

    found = _one(check_findings(root, "--diff", base), "new-dependency/undeclared-new-dependency")

    assert found["path"] == "docs/components/alpha.md"
    assert "added an import of shared" in found["message"]
    assert "new-dependency/undeclared-new-dependency" not in check_codes(
        root, "--diff", base, "--committed-only"
    )


def test_committed_only_reads_the_new_side_of_an_import_at_head(tmp_path: Path) -> None:
    root, base = _two_components(tmp_path)
    git(root, "checkout", "-q", "-b", "feature")
    write(root, "src/mylib/alpha.py", ALPHA)
    commit_all(root, "feature adds the import", when=_at(2))
    write(root, "src/mylib/alpha.py", "def run() -> None:\n    pass\n")
    gained = "new-dependency/undeclared-new-dependency"

    assert gained not in check_codes(root, "--diff", base)
    assert gained in check_codes(root, "--diff", base, "--committed-only")


def test_the_edge_is_new_against_the_merge_base_not_the_base_branch_tip(tmp_path: Path) -> None:
    root, base = _two_components(tmp_path)
    git(root, "checkout", "-q", "-b", "feature")
    write(root, "src/mylib/alpha.py", ALPHA)
    commit_all(root, "feature adds the import", when=_at(2))
    git(root, "checkout", "-q", "main")
    write(root, "src/mylib/alpha.py", ALPHA)
    commit_all(root, "main added it too", when=_at(3))
    git(root, "checkout", "-q", "feature")

    codes = check_codes(root, "--diff", "main")

    assert "new-dependency/undeclared-new-dependency" in codes
    assert codes == check_codes(root, "--diff", base)
