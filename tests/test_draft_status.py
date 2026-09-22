"""`status: draft` excuses an unfinished doc, not one that is wrong about something outside it."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_CLI = (
    "import typer\n\napp = typer.Typer()\n\n\n"
    "@app.command()\ndef check() -> None:\n    pass\n\n\n"
    "@app.command()\ndef status() -> None:\n    pass\n"
)
_RETIREMENT = (
    "---\nid: retire-render\ntitle: Retire render\nstatus: stable\n"
    "retires:\n  - id: render-command\n    kind: cli-command\n    surface_identity: render\n"
    "    matches:\n      - tool render\n    guidance: Use `tool check` instead.\n"
    "---\n\n# Retire render\n\n## Status\n\nAccepted.\n\n## Decision\n\nRemove it.\n\n"
    "## Consequences\n\nOne command fewer.\n"
)
_BODY = (
    "The widget wraps the gate. <!-- claim:no-such-claim -->\n\n"
    "Run `tool publish` to ship it, or the older tool render.\n\n"
    "It calls `load_graph()` first.\n\n"
    "See notes.md for the rest.\n"
)
_CERTAIN = [
    "claim-provenance/unknown-claim-ref",
    "code-references/unknown-command",
    "prose-file-reference/unlinked-reference",
    "retired-references/retired-reference",
]
_HINT = "code-references/unknown-symbol"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _widget(root: Path, status: str) -> None:
    _write(
        root,
        "docs/components/widget.md",
        f"---\nid: widget\ntitle: Widget\nstatus: {status}\n---\n\n# Widget\n\n{_BODY}",
    )


def _repo(root: Path) -> Path:
    _write(
        root,
        "irminsul.toml",
        'project_name = "tool"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[frameworks]\ncommand_names = ["tool"]\n'
        '[checks]\nenabled = ["frontmatter", "claim-provenance", "code-references", '
        '"prose-file-reference", "retired-references"]\n',
    )
    _write(root, "src/cli.py", _CLI)
    _write(root, "docs/decisions/retire-render.md", _RETIREMENT)
    return root


def _on_widget(root: Path, *extra: str) -> tuple[int, dict[str, str]]:
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root), *extra])
    findings = json.loads(result.output)["findings"]
    return result.exit_code, {
        f["code"]: f["severity"] for f in findings if f["path"] == "docs/components/widget.md"
    }


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def test_a_draft_reports_the_certain_findings_a_stable_doc_does(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    _widget(root, "stable")
    stable_exit, stable = _on_widget(root)
    _widget(root, "draft")
    draft_exit, draft = _on_widget(root)

    assert sorted(code for code, severity in stable.items() if severity == "error") == _CERTAIN
    assert sorted(code for code, severity in draft.items() if severity == "error") == _CERTAIN
    assert (stable_exit, draft_exit) == (1, 1)


def test_a_draft_is_not_asked_the_hints(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    _widget(root, "stable")
    _, stable = _on_widget(root)
    _widget(root, "draft")
    _, draft = _on_widget(root)

    assert stable.get(_HINT) == "warning"
    assert _HINT not in draft


def test_a_deprecated_doc_is_not_read(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _widget(root, "deprecated")

    _, deprecated = _on_widget(root)

    assert not set(deprecated) & {*_CERTAIN, _HINT}


def test_flipping_a_stable_doc_to_draft_clears_nothing(tmp_path: Path) -> None:
    """The flip is one word of frontmatter in the change under review, so neither a plain
    run nor the pull request's `--diff` run may go green because of it."""
    root = _repo(tmp_path)
    _git(root, "init", "-q")
    _widget(root, "stable")
    base = _commit(root, "a stable doc that is wrong about four things")
    _widget(root, "draft")
    _commit(root, "flip it to draft")

    plain_exit, plain = _on_widget(root)
    diff_exit, under_diff = _on_widget(root, "--diff", base)

    assert sorted(code for code, severity in plain.items() if severity == "error") == _CERTAIN
    assert sorted(code for code, sev in under_diff.items() if sev == "error") == _CERTAIN
    assert (plain_exit, diff_exit) == (1, 1)
