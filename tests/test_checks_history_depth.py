"""A checkout too shallow to answer the enabled checks must say so, not stay quiet.

`actions/checkout` clones to depth 1 by default, and the checks that read `git log`
find nothing there — a silence indistinguishable from a healthy tree.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import commit_all, gate_codes, git_init

runner = CliRunner()


def _repo(root: Path, enabled: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git_init(root)
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        f"[checks]\nenabled = {enabled}\n",
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\n---\n\n# Widget\n",
        encoding="utf-8",
    )
    commit_all(root, "seed")
    return root


def _codes(root: Path) -> str:
    return runner.invoke(app, ["check", "--path", str(root)]).output


def _remove_git_dir(root: Path) -> None:
    """Delete `.git` portably.

    `rm -rf` is not a program on Windows outside a Bash shell, and git marks its pack
    objects read-only, which `shutil.rmtree` cannot unlink without clearing the bit.
    """

    def _clear_readonly(func, path, _exc):  # type: ignore[no-untyped-def]
        Path(path).chmod(stat.S_IWRITE)
        func(path)

    shutil.rmtree(root / ".git", onexc=_clear_readonly)


def test_a_shallow_clone_is_an_error_when_a_check_reads_history(tmp_path: Path) -> None:
    origin = _repo(tmp_path / "origin", '["frontmatter", "mtime-drift"]')
    (origin / "docs" / "components" / "widget.md").write_text(
        "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\n---\n\n# Widget\n\nMore.\n",
        encoding="utf-8",
    )
    commit_all(origin, "second")

    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.resolve().as_uri(), str(shallow)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (shallow / ".git" / "shallow").exists(), "the fixture is not actually shallow"

    result = runner.invoke(app, ["check", "--path", str(shallow)])
    assert "history-depth/shallow-clone" in result.output
    assert "mtime-drift" in result.output
    assert result.exit_code == 1


def test_a_full_clone_says_nothing_about_history_depth(tmp_path: Path) -> None:
    root = _repo(tmp_path / "full", '["frontmatter", "mtime-drift"]')
    assert "history-depth" not in _codes(root)


def test_no_history_is_only_a_hint(tmp_path: Path) -> None:
    root = tmp_path / "loose"
    _repo(root, '["frontmatter", "mtime-drift"]')
    _remove_git_dir(root)

    result = runner.invoke(app, ["check", "--path", str(root)])
    assert "history-depth/no-history" in result.output
    assert result.exit_code == 0


def test_no_history_offers_its_own_answer_rather_than_disabling_checks(tmp_path: Path) -> None:
    """Disabling a check answers this finding with a gate weakening of its own."""
    root = tmp_path / "loose"
    _repo(root, '["frontmatter", "mtime-drift"]')
    _remove_git_dir(root)

    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root)])
    (finding,) = [
        f for f in json.loads(result.output)["findings"] if f["code"] == "history-depth/no-history"
    ]
    assert (
        finding["suggestion"] == "commit the tree, or run --only with checks that read no history"
    )
    assert finding["answer"] == "fix"


def test_nothing_is_reported_when_no_enabled_check_reads_history(tmp_path: Path) -> None:
    root = tmp_path / "quiet"
    _repo(root, '["frontmatter"]')
    _remove_git_dir(root)

    assert "history-depth" not in _codes(root)


def _shallow_clone(tmp_path: Path, enabled: str) -> Path:
    origin = _repo(tmp_path / "origin", enabled)
    (origin / "docs" / "components" / "widget.md").write_text(
        "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\n---\n\n# Widget\n\nMore.\n",
        encoding="utf-8",
    )
    commit_all(origin, "second")
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.resolve().as_uri(), str(shallow)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (shallow / ".git" / "shallow").exists(), "the fixture is not actually shallow"
    return shallow


def test_a_lifecycle_gate_does_not_pass_on_history_it_cannot_read(tmp_path: Path) -> None:
    """`rfc-follow-through` answers from commit history and the gates block on its findings, so
    a shallow clone turned it into a no-op and the gate reported success on the absence of
    evidence. The CLI had this guard from the start; the gates assembled their own run."""
    shallow = _shallow_clone(tmp_path, '["frontmatter", "rfc-follow-through"]')

    assert "history-depth/shallow-clone" in gate_codes(shallow)


def test_the_mcp_server_reports_a_shallow_clone(tmp_path: Path) -> None:
    """The guard reaches the entry point an agent asks, not only the CLI.

    An agent that calls the server and is told nothing is wrong acts on that, so a checkout
    whose history-reading checks can see nothing has to say so here too. Kept as its own test
    because moving two MCP tests onto copied fixtures is what made room for it: those assert
    that a green fixture is green, and this asserts that a blind checkout is not.
    """
    from irminsul.config import load
    from irminsul.mcp_server import check_json

    shallow = _shallow_clone(tmp_path, '["frontmatter", "rfc-follow-through"]')

    data = json.loads(check_json(shallow, load(shallow / "irminsul.toml")))

    assert "history-depth/shallow-clone" in {finding["code"] for finding in data["findings"]}
    assert data["summary"]["errors"] >= 1


def test_a_gate_running_no_history_check_gains_no_shallow_failure(tmp_path: Path) -> None:
    """The guard is self-scoping, and that is what keeps it from spreading. A workflow that
    was not asking a historical question does not start failing because the check list grew."""
    shallow = _shallow_clone(tmp_path, '["frontmatter"]')

    assert not {code for code in gate_codes(shallow) if code.startswith("history-depth/")}


def test_a_shallow_clone_is_never_pre_existing_under_delta(tmp_path: Path) -> None:
    """The scratch worktree `--delta` checks the base out into is as shallow as the clone,
    so the base run reports the same finding. It is not debt — the checks that read
    history are blind on both sides — so it stays new and the run still fails."""
    shallow = _shallow_clone(tmp_path, '["frontmatter", "mtime-drift"]')
    doc = shallow / "docs" / "components" / "widget.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nEdited.\n", encoding="utf-8")

    result = runner.invoke(app, ["check", "--delta", "--path", str(shallow)])

    assert "history-depth/shallow-clone" in result.output
    assert result.exit_code == 1


def test_a_baseline_never_records_or_hides_a_shallow_clone(tmp_path: Path) -> None:
    """The finding says the checkout cannot answer the checks that read history. A
    baseline written in a shallow CI checkout recorded it, and every later shallow run was
    then green with those checks blind — the silence this pass exists to break."""
    shallow = _shallow_clone(tmp_path, '["frontmatter", "mtime-drift"]')

    result = runner.invoke(app, ["baseline", "init", "--path", str(shallow)])
    assert result.exit_code == 0, result.output
    recorded = json.loads((shallow / ".irminsul-baseline.json").read_text(encoding="utf-8"))
    assert [entry["check"] for entry in recorded["findings"]] == []

    # A hand-written entry does not hide it either.
    message = next(
        f["message"]
        for f in json.loads(
            runner.invoke(app, ["check", "--format", "json", "--path", str(shallow)]).output
        )["findings"]
        if f["code"] == "history-depth/shallow-clone"
    )
    recorded["findings"] = [{"check": "history-depth", "path": ".", "message": message}]
    (shallow / ".irminsul-baseline.json").write_text(json.dumps(recorded), encoding="utf-8")
    result = runner.invoke(app, ["check", "--path", str(shallow)])
    assert "history-depth/shallow-clone" in result.output
    assert result.exit_code == 1


def test_list_baseline_calls_an_entry_that_hides_nothing_fixed(tmp_path: Path) -> None:
    """`list baseline` called an entry hidden whenever a live finding matched it. A
    hand-written `history-depth` entry hides nothing, so it read as hidden while `check`
    counted it stale and `irminsul baseline update` would remove it; one rule now decides both."""
    shallow = _shallow_clone(tmp_path, '["frontmatter", "mtime-drift"]')
    message = next(
        f["message"]
        for f in json.loads(
            runner.invoke(app, ["check", "--format", "json", "--path", str(shallow)]).output
        )["findings"]
        if f["code"] == "history-depth/shallow-clone"
    )
    (shallow / ".irminsul-baseline.json").write_text(
        json.dumps(
            {
                "version": 1,
                "findings": [{"check": "history-depth", "path": ".", "message": message}],
            }
        ),
        encoding="utf-8",
    )

    listed = runner.invoke(app, ["list", "baseline", "--format", "json", "--path", str(shallow)])
    checked = json.loads(
        runner.invoke(app, ["check", "--format", "json", "--path", str(shallow)]).output
    )

    assert [row["state"] for row in json.loads(listed.output)["entries"]] == ["fixed"]
    assert checked["baseline"]["stale"] == 1
