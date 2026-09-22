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

runner = CliRunner()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def _repo(root: Path, enabled: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root.parent, "init", "-q", root.name)
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        f"[checks]\nenabled = {enabled}\n",
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "widget.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: widget\ntitle: Widget\nstatus: stable\n---\n\n# Widget\n", encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", "seed")
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
        "---\nid: widget\ntitle: Widget\nstatus: stable\n---\n\n# Widget\n\nMore.\n",
        encoding="utf-8",
    )
    _git(origin, "add", "-A")
    _git(origin, "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", "second")

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


def test_nothing_is_reported_when_no_enabled_check_reads_history(tmp_path: Path) -> None:
    root = tmp_path / "quiet"
    _repo(root, '["frontmatter"]')
    _remove_git_dir(root)

    assert "history-depth" not in _codes(root)


def _shallow_clone(tmp_path: Path, enabled: str) -> Path:
    origin = _repo(tmp_path / "origin", enabled)
    (origin / "docs" / "components" / "widget.md").write_text(
        "---\nid: widget\ntitle: Widget\nstatus: stable\n---\n\n# Widget\n\nMore.\n",
        encoding="utf-8",
    )
    _git(origin, "add", "-A")
    _git(origin, "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", "second")
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.resolve().as_uri(), str(shallow)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (shallow / ".git" / "shallow").exists(), "the fixture is not actually shallow"
    return shallow


def _gate_codes(root: Path) -> set[str]:
    """What the change-lifecycle gates block on, which is `enabled_findings`."""
    from irminsul.checks.pipeline import enabled_findings
    from irminsul.config import load
    from irminsul.docgraph import build_graph

    config = load(root / "irminsul.toml")
    return {f.code for f in enabled_findings(build_graph(root, config))}


def test_a_lifecycle_gate_does_not_pass_on_history_it_cannot_read(tmp_path: Path) -> None:
    """`change-binding` answers from commit history and the gates block on its findings, so a
    shallow clone turned it into a no-op and the gate reported success on the absence of
    evidence. The CLI had this guard from the start; the gates assembled their own run."""
    shallow = _shallow_clone(tmp_path, '["frontmatter", "change-binding"]')

    assert "history-depth/shallow-clone" in _gate_codes(shallow)


def test_the_mcp_server_reports_a_shallow_clone(tmp_path: Path) -> None:
    """The guard reaches the entry point an agent asks, not only the CLI.

    An agent that calls the server and is told nothing is wrong acts on that, so a checkout
    whose history-reading checks can see nothing has to say so here too. Kept as its own test
    because moving two MCP tests onto copied fixtures is what made room for it: those assert
    that a green fixture is green, and this asserts that a blind checkout is not.
    """
    from irminsul.config import load
    from irminsul.mcp_server import check_json

    shallow = _shallow_clone(tmp_path, '["frontmatter", "change-binding"]')

    data = json.loads(check_json(shallow, load(shallow / "irminsul.toml")))

    assert "history-depth/shallow-clone" in {finding["code"] for finding in data["findings"]}
    assert data["summary"]["errors"] >= 1


def test_a_gate_running_no_history_check_gains_no_shallow_failure(tmp_path: Path) -> None:
    """The guard is self-scoping, and that is what keeps it from spreading. A workflow that
    was not asking a historical question does not start failing because the check list grew."""
    shallow = _shallow_clone(tmp_path, '["frontmatter"]')

    assert not {code for code in _gate_codes(shallow) if code.startswith("history-depth/")}
