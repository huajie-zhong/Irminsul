"""What `context` claims to have validated, and what it refuses to claim.

Two failures these pin. A mode that ran no checks used to report that the checks passed,
with zero errors — a green that measured nothing; now it reports no verdict at all. And after an edit, every pre-existing
violation in the tree was reported as this change's problem, so an agent could not tell
what it had broken from what it had inherited.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import commit_all, config_toml, git, git_init, write

runner = CliRunner()

_CONFIG = config_toml(project_name="v", source_roots=["src"], enabled=["frontmatter", "uniqueness"])
_DOC = """---
id: core
title: Core
status: stable
summary: A test doc.
describes:
  - src/core.py
---

# Core

The core component.
"""


def _repo(root: Path) -> Path:
    write(root, "irminsul.toml", _CONFIG)
    write(root, "src/core.py", "X = 1\n")
    write(root, "docs/components/core.md", _DOC)
    git_init(root)
    commit_all(root, "seed")
    return root


def _broken(root: Path, name: str) -> None:
    """A doc with no frontmatter: one certain finding, owned by nothing this run edits."""
    write(root, f"docs/components/{name}.md", f"# {name} without frontmatter\n")


def _ctx(root: Path, *args: str) -> tuple[int, dict]:
    result = runner.invoke(app, ["context", *args, "--format", "json", "--path", str(root)])
    return result.exit_code, json.loads(result.output)


def _plain(root: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["context", *args, "--path", str(root)])
    return result.exit_code, result.output


# --- the path packet: a retrieval step that validates nothing ------------------------


def test_the_packet_says_it_ran_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    code, data = _ctx(root, "src/core.py")

    assert code == 0
    assert "validation" not in data


def test_the_packet_does_not_fabricate_a_clean_tree(tmp_path: Path) -> None:
    """The tree is broken and the packet still exits 0 — because producing it succeeded,
    not because the repository is well. It must not say the latter."""
    root = _repo(tmp_path)
    _broken(root, "legacy")
    commit_all(root, "a doc with no frontmatter")

    code, data = _ctx(root, "src/core.py")

    assert code == 0
    assert "validation" not in data


def test_the_packet_findings_are_absent_not_empty(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _broken(root, "legacy")

    _, data = _ctx(root, "src/core.py")

    assert data["results"]
    assert all("findings" not in result for result in data["results"])


def test_the_plain_packet_states_no_verdict(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    code, out = _plain(root, "src/core.py")

    assert code == 0
    assert "Repository validation" not in out
    assert "findings:" not in out


# --- after-edit: two verdicts, separately answerable -----------------------------


def test_after_edit_still_runs_the_checks(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "src/core.py", "X = 2\n")

    code, data = _ctx(root, "--after-edit")

    assert code == 0
    assert data["validation"]["repository"]["state"] == "passed"
    assert data["validation"]["repository"]["errors"] == 0
    assert data["validation"]["change"]["state"] == "passed"
    assert data["validation"]["change"]["new_errors"] == 0


def test_an_inherited_error_is_not_charged_to_this_change(tmp_path: Path) -> None:
    """The repository verdict still reports it, and the exit code no longer does: an
    agent cannot fix what it did not break, and a gate that always fails teaches nothing."""
    root = _repo(tmp_path)
    _broken(root, "legacy")
    commit_all(root, "inherit a broken doc")
    write(root, "src/core.py", "X = 2\n")

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["repository"]["state"] == "failed"
    assert data["validation"]["repository"]["errors"] > 0
    assert data["validation"]["change"] == {
        "state": "passed",
        "new_errors": 0,
        "baseline": "HEAD",
        "reason": None,
        "note": data["validation"]["change"]["note"],
    }
    assert "no base was given" in data["validation"]["change"]["note"]
    assert code == 0


def test_an_error_this_change_introduced_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _broken(root, "fresh")

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["change"]["state"] == "failed"
    assert data["validation"]["change"]["new_errors"] > 0
    assert code == 1


def test_removing_a_pre_existing_error_is_not_a_new_one(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _broken(root, "legacy")
    commit_all(root, "inherit a broken doc")
    (root / "docs" / "components" / "legacy.md").unlink()

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["repository"]["state"] == "passed"
    assert data["validation"]["change"]["state"] == "passed"
    assert code == 0


def test_a_committed_edit_has_no_baseline_in_head(tmp_path: Path) -> None:
    """HEAD already holds the change, so comparing with it would find nothing and report
    a zero it never measured. The repository verdict carries the run instead."""
    root = _repo(tmp_path)
    _broken(root, "fresh")
    commit_all(root, "commit the broken doc")

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["change"]["state"] == "not_run"
    assert data["validation"]["change"]["new_errors"] is None
    assert "nothing to compare" in data["validation"]["change"]["reason"]
    assert data["validation"]["repository"]["state"] == "failed"
    assert code == 1


def test_base_ref_reaches_a_committed_edit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")
    _broken(root, "fresh")
    commit_all(root, "commit the broken doc")

    code, data = _ctx(root, "--after-edit", "--base-ref", base)

    assert data["validation"]["change"]["state"] == "failed"
    assert data["validation"]["change"]["new_errors"] > 0
    assert data["validation"]["change"]["baseline"] == base
    assert code == 1


def test_an_unresolvable_base_ref_is_reported_not_guessed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "src/core.py", "X = 2\n")

    code, data = _ctx(root, "--after-edit", "--base-ref", "no-such-rev")

    assert data["validation"]["change"]["state"] == "not_run"
    assert data["validation"]["change"]["new_errors"] is None
    assert data["validation"]["repository"]["state"] == "passed"
    assert code == 0


def test_an_unresolvable_base_ref_is_named_in_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    write(root, "src/core.py", "X = 2\n")
    monkeypatch.delenv("IRMINSUL_BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)

    _, data = _ctx(root, "--after-edit", "--base-ref", "no-such-rev")
    plain = _plain(root, "--after-edit", "--base-ref", "no-such-rev")[1]

    reason = data["validation"]["change"]["reason"]
    assert "'no-such-rev' could not be resolved" in reason
    assert "no diff baseline" not in reason
    assert f"reason: {reason}" in plain

    monkeypatch.setenv("IRMINSUL_BASE_REF", "no-such-ci-ref")
    _, from_env = _ctx(root, "--after-edit")
    assert "'no-such-ci-ref' could not be resolved" in from_env["validation"]["change"]["reason"]


def test_after_edit_without_git_refuses_rather_than_reporting(tmp_path: Path) -> None:
    """After-edit reads the changed set from git before it validates anything, so with no
    repository it cannot start. It says so instead of reporting an empty change set."""
    root = tmp_path / "nogit"
    write(root, "irminsul.toml", _CONFIG)
    write(root, "src/core.py", "X = 1\n")
    write(root, "docs/components/core.md", _DOC)
    _broken(root, "fresh")

    result = runner.invoke(app, ["context", "--after-edit", "--path", str(root)])

    assert result.exit_code != 0
    assert "git" in result.output.lower()


def test_a_config_change_that_disables_a_check_is_measured_whole_tree(tmp_path: Path) -> None:
    """Turning a check off is not a per-file edit, so only a whole-tree comparison sees
    it: the findings it used to produce disappear, and none is new."""
    root = _repo(tmp_path)
    _broken(root, "legacy")
    commit_all(root, "inherit a broken doc")
    write(root, "irminsul.toml", _CONFIG.replace('"frontmatter", "uniqueness"', '"uniqueness"'))

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["repository"]["state"] == "passed"
    assert data["validation"]["change"]["state"] == "passed"
    assert code == 0


def test_plain_and_json_agree_after_an_edit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _broken(root, "legacy")
    commit_all(root, "inherit a broken doc")
    write(root, "src/core.py", "X = 2\n")

    json_code, data = _ctx(root, "--after-edit")
    plain_code, out = _plain(root, "--after-edit")

    assert json_code == plain_code
    repository, change = data["validation"]["repository"], data["validation"]["change"]
    assert f"Repository validation: {repository['state']}" in out
    assert f"({repository['errors']} errors, {repository['warnings']} warnings)" in out
    assert f"Change validation: {change['state']}" in out
    assert f"({change['new_errors']} new errors vs {change['baseline']})" in out


# --- after an edit, the repository verdict is plain `check`'s ---------------------------


_UNUSED_IGNORE = '\n<!-- irminsul:ignore uniqueness reason="nothing to hide" -->\n'


def test_after_edit_audits_ignore_comments_as_check_does(tmp_path: Path) -> None:
    """An ignore comment that suppresses nothing fails `check`. The run `--after-edit`
    assembled for itself never audited a comment, so it called that repository clean."""
    root = _repo(tmp_path)
    write(root, "docs/components/core.md", _DOC + _UNUSED_IGNORE)

    code, data = _ctx(root, "--after-edit")

    codes = {finding["code"] for finding in data["findings"]}
    assert "ignore-comment/unused" in codes
    assert data["validation"]["repository"]["state"] == "failed"
    assert code == 1
    assert runner.invoke(app, ["check", "--path", str(root)]).exit_code == 1


def test_after_edit_findings_carry_the_shared_record_shape(tmp_path: Path) -> None:
    """The same record `check --format json` emits, so an agent reads one shape: the class
    the code declares beside the one this occurrence enforces as, the structured data, and
    whether `fix` remediates it."""
    root = _repo(tmp_path)
    write(
        root,
        "docs/components/core.md",
        _DOC.replace("status: stable\nsummary: A test doc.\n", "status: draft\n"),
    )

    _, data = _ctx(root, "--after-edit")

    record = next(
        finding for finding in data["findings"] if finding["code"] == "frontmatter/missing-summary"
    )
    assert record["class"] == "certain"
    assert record["effective_class"] == "hint"
    assert record["severity"] == "warning"
    assert "data" in record
    assert "fixable" in record


def test_after_edit_applies_the_baseline_as_check_does(tmp_path: Path) -> None:
    """A baselined finding does not fail `check`, so it does not fail the repository verdict
    here either — and the report says how many the baseline hid."""
    root = _repo(tmp_path)
    _broken(root, "legacy")
    assert runner.invoke(app, ["baseline", "init", "--path", str(root)]).exit_code == 0
    commit_all(root, "adopt with a baseline")
    write(root, "src/core.py", "X = 2\n")

    code, data = _ctx(root, "--after-edit")

    repository = data["validation"]["repository"]
    assert repository["state"] == "passed"
    assert repository["errors"] == 0
    assert repository["baseline"]["applied"] is True
    assert repository["baseline"]["suppressed"] == 1
    assert code == 0
    _, out = _plain(root, "--after-edit")
    assert "baseline: 1 certain finding(s) hidden by .irminsul-baseline.json" in out


def test_after_edit_refuses_an_unreadable_baseline(tmp_path: Path) -> None:
    """`check` exits 2 on a baseline it cannot read rather than treating it as absent;
    reporting a verdict over it here would be a verdict `check` refuses to give."""
    root = _repo(tmp_path)
    write(root, ".irminsul-baseline.json", "{not json")
    write(root, "src/core.py", "X = 2\n")

    code, out = _plain(root, "--after-edit")

    assert code == 2
    assert "could not read baseline" in out


# --- with no base, the checks that judge a change did not run -------------------------


def _debt_repo(root: Path) -> Path:
    _repo(root)
    write(root, "src/legacy.py", "X = 1\n")
    write(root, ".irminsul-adoption.json", '{"version": 1, "unowned": ["src/legacy.py"]}\n')
    commit_all(root, "adopt")
    write(root, "src/legacy.py", "X = 2\n")
    return root


def test_with_no_base_the_verdict_says_which_checks_did_not_run(tmp_path: Path) -> None:
    """`passed (0 new errors vs HEAD)` is true of what was judged and silent about what was
    not: `diff-integrity` is the pass that fails an edit to recorded debt, and without a base
    it never ran. The verdict is unchanged; it now says so and names the command that runs
    them."""
    root = _debt_repo(tmp_path)

    code, data = _ctx(root, "--after-edit")
    change = data["validation"]["change"]

    assert (change["state"], change["new_errors"], change["baseline"]) == ("passed", 0, "HEAD")
    assert data["validation"]["repository"]["errors"] == 0
    assert code == 0
    for name in ("co-change", "diff-integrity", "new-dependency"):
        assert f"`{name}`" in change["note"]
    assert "no base was given" in change["note"]
    assert "--base-ref <base>" in change["note"] and "--base-ref HEAD" in change["note"]

    _, out = _plain(root, "--after-edit")
    assert "Change validation: passed (0 new errors vs HEAD)\n  note: no base was given" in out


def test_the_command_the_note_names_runs_the_checks_it_says_did_not(tmp_path: Path) -> None:
    root = _debt_repo(tmp_path)

    code, data = _ctx(root, "--after-edit", "--base-ref", "HEAD")
    change = data["validation"]["change"]

    assert (change["state"], change["new_errors"], change["note"]) == ("failed", 1, None)
    assert data["validation"]["repository"]["errors"] == 1
    assert code == 1
