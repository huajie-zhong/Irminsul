"""A draft doc may be unfinished; it may not be wrong about something outside it.

`status: draft` used to demote every certain finding that landed on the doc, which made
one word of frontmatter the cheapest way to turn an error into a warning.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.pipeline import _drafts_exempt
from irminsul.cli import app

runner = CliRunner()

_CONFIG = (
    'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
    '[checks]\nenabled = ["frontmatter", "links", "boundary"]\n'
)
_INDEX = (
    "---\nid: components\ntitle: Components\nstatus: stable\n---\n\n# Components\n\n- [W](w.md)\n"
)


def _repo(tmp_path: Path, status: str, body: str) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "components").mkdir(parents=True)
    (root / "irminsul.toml").write_text(_CONFIG, encoding="utf-8")
    (root / "docs" / "components" / "INDEX.md").write_text(_INDEX, encoding="utf-8")
    (root / "docs" / "components" / "w.md").write_text(
        f"---\nid: w\ntitle: W\nstatus: {status}\n---\n\n# W\n\n{body}\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    return root


_BROKEN_LINK = "See [nothing](nowhere.md).\n\n## Scope & Limitations\n\nNone."
_UNFINISHED = "Still writing this."


def _run(root: Path) -> tuple[int, str]:
    result = runner.invoke(app, ["check", "--path", str(root)])
    return result.exit_code, result.output


def test_a_draft_does_not_excuse_a_broken_link(tmp_path: Path) -> None:
    code, output = _run(_repo(tmp_path, "draft", _BROKEN_LINK))
    assert "links/broken-link" in output
    assert code == 1, "flipping to draft silenced a finding about the world outside the doc"


def test_a_stable_doc_reports_the_same_broken_link(tmp_path: Path) -> None:
    code, output = _run(_repo(tmp_path, "stable", _BROKEN_LINK))
    assert "links/broken-link" in output
    assert code == 1


def test_a_draft_is_still_allowed_to_be_unfinished(tmp_path: Path) -> None:
    code, output = _run(_repo(tmp_path, "draft", _UNFINISHED))
    assert "boundary/missing-scope-limitations" in output
    assert "warning" in output
    assert code == 0


def test_the_same_unfinished_doc_fails_once_stable(tmp_path: Path) -> None:
    code, output = _run(_repo(tmp_path, "stable", _UNFINISHED))
    assert "boundary/missing-scope-limitations" in output
    assert code == 1


def test_every_draft_exempt_code_is_a_code_some_check_explains() -> None:
    from irminsul.checks.pipeline import _all_checks

    known = {code for cls in _all_checks() for code in cls.explanations}
    assert _drafts_exempt(), "no check declares drafts_exempt, so the rule is unreachable"
    assert _drafts_exempt() <= known, sorted(_drafts_exempt() - known)


def test_an_error_with_an_unclassed_code_still_fails_the_run() -> None:
    """A code missing from its check's `classes` map is a mistake, and the failure mode for
    a mistake here has to be loud. Returning None made it print red and exit 0."""
    from pathlib import Path

    from irminsul.checks.base import Finding, FindingClass, Severity
    from irminsul.checks.pipeline import effective_class

    unclassed = Finding(
        check="nowhere",
        code="nowhere/unregistered",
        severity=Severity.error,
        message="something broke",
        path=Path("docs/a.md"),
    )

    assert effective_class(unclassed) is FindingClass.certain
