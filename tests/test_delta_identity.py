"""What counts as the *same* finding across two runs.

A fingerprint is `(check, path, message)`, and some messages carry a line number —
`duplicate-block` says "repeats the one at line 9". Inserting an unrelated paragraph above
the pair rewrote that message, so an untouched violation came back as newly introduced and
`context --after-edit` failed the change for something it had not done.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.base import Finding, Severity
from irminsul.cli import app
from irminsul.delta import compute_delta

runner = CliRunner()

_BLOCK = "Source discovery walks every configured root and skips the paths an ignore list names."
_CONFIG = (
    'project_name = "d"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
    '[checks]\nenabled = ["frontmatter", "duplicate-block"]\n'
)


def _finding(message: str, path: str = "docs/a.md", code: str = "links/broken-link") -> Finding:
    return Finding(
        check=code.split("/")[0],
        code=code,
        severity=Severity.error,
        message=message,
        path=Path(path),
    )


def test_a_message_that_only_moved_is_pre_existing() -> None:
    base = [_finding("block repeats the one at line 9 verbatim")]
    head = [_finding("block repeats the one at line 11 verbatim")]

    result = compute_delta(head, base)

    assert result.new == []
    assert result.pre_existing == 1


def test_an_additional_occurrence_of_the_same_kind_is_new() -> None:
    """The pairing counts occurrences, so a second violation of the same code in the same
    file is still reported — otherwise the fix would hide real regressions."""
    base = [_finding("block repeats the one at line 9 verbatim")]
    head = [
        _finding("block repeats the one at line 11 verbatim"),
        _finding("block repeats the one at line 30 verbatim"),
    ]

    result = compute_delta(head, base)

    assert len(result.new) == 1
    assert result.pre_existing == 1


def test_the_same_kind_in_a_different_file_is_new() -> None:
    base = [_finding("block repeats the one at line 9 verbatim", path="docs/a.md")]
    head = [_finding("block repeats the one at line 9 verbatim", path="docs/b.md")]

    result = compute_delta(head, base)

    assert [f.path.as_posix() for f in result.new] == ["docs/b.md"]
    assert result.pre_existing == 0


def test_a_meaningful_figure_changing_is_new() -> None:
    """The figure *is* the violation here. Blanking every digit flattened `widened from 30
    to 100` and `widened from 30 to 3650` to one string, so a worse weakening of the gate
    read as the one already recorded."""
    base = [_finding("mtime_drift_days was widened from 30 to 100", code="diff-integrity/x")]
    head = [_finding("mtime_drift_days was widened from 30 to 3650", code="diff-integrity/x")]

    result = compute_delta(head, base)

    assert len(result.new) == 1
    assert result.pre_existing == 0


def test_two_findings_differing_only_in_a_meaningful_figure_stay_distinct() -> None:
    """Same check, code and path; different numbers that mean different things. Neither
    may absorb the other, in either direction."""
    base = [_finding("threshold 30 exceeded"), _finding("threshold 90 exceeded")]
    head = [_finding("threshold 30 exceeded"), _finding("threshold 3650 exceeded")]

    result = compute_delta(head, base)

    assert [f.message for f in result.new] == ["threshold 3650 exceeded"]
    assert result.pre_existing == 1


def test_one_of_two_identical_violations_is_new() -> None:
    """Cardinality is carried: the baseline held one, the head holds two, so exactly one
    of them is introduced. Matching is one-to-one, not set membership."""
    base = [_finding("block repeats the one at line 9 verbatim")]
    head = [
        _finding("block repeats the one at line 9 verbatim"),
        _finding("block repeats the one at line 9 verbatim"),
    ]

    result = compute_delta(head, base)

    assert len(result.new) == 1
    assert result.pre_existing == 1


def test_a_removed_violation_does_not_pay_for_a_different_one(tmp_path: Path) -> None:
    """One broken link fixed and another introduced is a change, not a wash. The words
    differ, so nothing pairs them."""
    base = [_finding("link target 'old.md' does not exist")]
    head = [_finding("link target 'new.md' does not exist")]

    result = compute_delta(head, base)

    assert [f.message for f in result.new] == ["link target 'new.md' does not exist"]
    assert result.pre_existing == 0


def test_a_path_and_line_reference_is_treated_as_a_position(tmp_path: Path) -> None:
    """The other location idiom: `copies the one at docs/a.md:9`."""
    base = [_finding("block copies the one at docs/a.md:9 verbatim")]
    head = [_finding("block copies the one at docs/a.md:31 verbatim")]

    result = compute_delta(head, base)

    assert result.new == []
    assert result.pre_existing == 1


def test_a_different_code_in_the_same_file_is_new() -> None:
    """The looser pass keys on the code as well, so one kind of problem going away does
    not pay for a different kind arriving. (The exact fingerprint does not carry the
    code — `(check, path, message)` — which is why the messages here differ too.)"""
    base = [_finding("target 'a.md' does not exist", code="links/broken-link")]
    head = [_finding("anchor '#x' does not exist", code="links/missing-anchor")]

    result = compute_delta(head, base)

    assert len(result.new) == 1


def test_an_exact_match_is_still_matched_first() -> None:
    """Exact fingerprints are consumed before the looser pairing, so one unchanged
    finding cannot absorb a different one of the same kind."""
    base = [_finding("at line 9"), _finding("at line 20")]
    head = [_finding("at line 9"), _finding("at line 44")]

    result = compute_delta(head, base)

    assert result.new == []
    assert result.pre_existing == 2


# --- end to end, through the command that reported the false positive ------------


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _doc(root: Path, extra: str = "") -> None:
    (root / "docs" / "guides").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "guides" / "a.md").write_text(
        f"---\nid: a\ntitle: A\nstatus: stable\n---\n\n# A\n\n{extra}{_BLOCK}\n\n{_BLOCK}\n",
        encoding="utf-8",
    )


def test_an_unrelated_insertion_does_not_introduce_the_old_violation(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(_CONFIG, encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("X = 1\n", encoding="utf-8")
    _doc(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", "base")

    _doc(tmp_path, extra="An unrelated paragraph that pushes the pair below it down.\n\n")

    result = runner.invoke(
        app, ["context", "--after-edit", "--format", "json", "--path", str(tmp_path)]
    )
    validation = json.loads(result.output)["validation"]

    assert validation["repository"]["state"] == "failed"
    assert validation["change"] == {
        "state": "passed",
        "new_errors": 0,
        "baseline": "HEAD",
        "reason": None,
    }
    assert result.exit_code == 0
