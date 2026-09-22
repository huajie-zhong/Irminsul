"""What `context` claims to have validated, and what it refuses to claim.

Two failures these pin. A stage that ran no checks used to report `checks_passed: true`
with zero errors — a green that measured nothing. And after an edit, every pre-existing
violation in the tree was reported as this change's problem, so an agent could not tell
what it had broken from what it had inherited.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_CONFIG = (
    'project_name = "v"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
    '[checks]\nenabled = ["frontmatter", "uniqueness"]\n'
)
_DOC = """---
id: core
title: Core
status: stable
describes:
  - src/core.py
---

# Core

The core component.
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _repo(root: Path) -> Path:
    _write(root, "irminsul.toml", _CONFIG)
    _write(root, "src/core.py", "X = 1\n")
    _write(root, "docs/components/core.md", _DOC)
    _git(root, "init", "-q")
    _commit(root, "seed")
    return root


def _broken(root: Path, name: str) -> None:
    """A doc with no frontmatter: one certain finding, owned by nothing this run edits."""
    _write(root, f"docs/components/{name}.md", f"# {name} without frontmatter\n")


def _ctx(root: Path, *args: str) -> tuple[int, dict]:
    result = runner.invoke(app, ["context", *args, "--format", "json", "--path", str(root)])
    return result.exit_code, json.loads(result.output)


def _plain(root: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["context", *args, "--path", str(root)])
    return result.exit_code, result.output


# --- before-edit: a retrieval step that validates nothing ------------------------


def test_before_edit_says_it_ran_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    code, data = _ctx(root, "--before-edit", "src/core.py")

    assert code == 0
    assert data["validation"]["repository"] == {
        "state": "not_run",
        "errors": None,
        "warnings": None,
    }
    assert data["validation"]["change"]["state"] == "not_run"
    assert data["validation"]["change"]["reason"]


def test_before_edit_does_not_fabricate_a_clean_tree(tmp_path: Path) -> None:
    """The tree is broken and before-edit still exits 0 — because producing the packet
    succeeded, not because the repository is well. It must not say the latter."""
    root = _repo(tmp_path)
    _broken(root, "legacy")
    _commit(root, "a doc with no frontmatter")

    code, data = _ctx(root, "--before-edit", "src/core.py")

    assert code == 0
    assert data["validation"]["repository"]["state"] == "not_run"
    assert data["validation"]["repository"]["errors"] is None
    assert "checks_passed" not in data["validation"]


def test_before_edit_findings_are_absent_not_empty(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _broken(root, "legacy")

    _, data = _ctx(root, "--before-edit", "src/core.py")

    assert [result["findings"] for result in data["results"]] == [None]


def test_before_edit_plain_output_says_not_run(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    code, out = _plain(root, "--before-edit", "src/core.py")

    assert code == 0
    assert "Repository validation: not run" in out
    assert "findings: not checked" in out
    assert "findings: (none)" not in out


# --- after-edit: two verdicts, separately answerable -----------------------------


def test_after_edit_still_runs_the_checks(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "src/core.py", "X = 2\n")

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
    _commit(root, "inherit a broken doc")
    _write(root, "src/core.py", "X = 2\n")

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["repository"]["state"] == "failed"
    assert data["validation"]["repository"]["errors"] > 0
    assert data["validation"]["change"] == {
        "state": "passed",
        "new_errors": 0,
        "baseline": "HEAD",
        "reason": None,
    }
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
    _commit(root, "inherit a broken doc")
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
    _commit(root, "commit the broken doc")

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["change"]["state"] == "not_run"
    assert data["validation"]["change"]["new_errors"] is None
    assert "nothing to compare" in data["validation"]["change"]["reason"]
    assert data["validation"]["repository"]["state"] == "failed"
    assert code == 1


def test_base_ref_reaches_a_committed_edit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    _broken(root, "fresh")
    _commit(root, "commit the broken doc")

    code, data = _ctx(root, "--after-edit", "--base-ref", base)

    assert data["validation"]["change"]["state"] == "failed"
    assert data["validation"]["change"]["new_errors"] > 0
    assert data["validation"]["change"]["baseline"] == base
    assert code == 1


def test_an_unresolvable_base_ref_is_reported_not_guessed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "src/core.py", "X = 2\n")

    code, data = _ctx(root, "--after-edit", "--base-ref", "no-such-rev")

    assert data["validation"]["change"]["state"] == "not_run"
    assert data["validation"]["change"]["new_errors"] is None
    assert data["validation"]["repository"]["state"] == "passed"
    assert code == 0


def test_after_edit_without_git_refuses_rather_than_reporting(tmp_path: Path) -> None:
    """After-edit reads the changed set from git before it validates anything, so with no
    repository it cannot start. It says so instead of reporting an empty change set."""
    root = tmp_path / "nogit"
    _write(root, "irminsul.toml", _CONFIG)
    _write(root, "src/core.py", "X = 1\n")
    _write(root, "docs/components/core.md", _DOC)
    _broken(root, "fresh")

    result = runner.invoke(app, ["context", "--after-edit", "--path", str(root)])

    assert result.exit_code != 0
    assert "git" in result.output.lower()


def test_a_config_change_that_disables_a_check_is_measured_whole_tree(tmp_path: Path) -> None:
    """Turning a check off is not a per-file edit, so only a whole-tree comparison sees
    it: the findings it used to produce disappear, and none is new."""
    root = _repo(tmp_path)
    _broken(root, "legacy")
    _commit(root, "inherit a broken doc")
    _write(root, "irminsul.toml", _CONFIG.replace('"frontmatter", "uniqueness"', '"uniqueness"'))

    code, data = _ctx(root, "--after-edit")

    assert data["validation"]["repository"]["state"] == "passed"
    assert data["validation"]["change"]["state"] == "passed"
    assert code == 0


def test_plain_and_json_agree_after_an_edit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _broken(root, "legacy")
    _commit(root, "inherit a broken doc")
    _write(root, "src/core.py", "X = 2\n")

    json_code, data = _ctx(root, "--after-edit")
    plain_code, out = _plain(root, "--after-edit")

    assert json_code == plain_code
    repository, change = data["validation"]["repository"], data["validation"]["change"]
    assert f"Repository validation: {repository['state']}" in out
    assert f"({repository['errors']} errors, {repository['warnings']} warnings)" in out
    assert f"Change validation: {change['state']}" in out
    assert f"({change['new_errors']} new errors vs {change['baseline']})" in out
