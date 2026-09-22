"""Ways the gate stopped gating while the sealed surface read as untouched.

Two shapes. In config, a check switched off through its own key or a threshold widened
under it: `checks.enabled` still lists the check, so the seal on that list saw nothing.
In CI, a step that still carries every flag but whose result is discarded — by
`continue-on-error`, by a condition that cannot be true, or by `|| true`.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .test_diff_integrity import _CONFIG, _commit, _repo, _workflow, _write

runner = CliRunner()

_ENABLED = '[checks]\nenabled = ["frontmatter", "links"]\n'
_GATE = '      - run: irminsul check --strict --diff "origin/main"\n'


def _codes(root: Path, base: str) -> list[str]:
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return sorted(f["code"] for f in json.loads(result.output)["findings"])


def _weakenings(root: Path, base: str) -> list[str]:
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return [
        f["message"]
        for f in json.loads(result.output)["findings"]
        if f["code"] == "diff-integrity/gate-weakened"
    ]


# --- config: a check switched off without leaving checks.enabled -----------------


def _config_repo(root: Path, extra: str = "") -> str:
    _repo(root)
    _write(root, "irminsul.toml", _CONFIG + _ENABLED + extra)
    return _commit(root, "base")


def _reconfigure(root: Path, extra: str) -> None:
    _write(root, "irminsul.toml", _CONFIG + _ENABLED + extra)
    _commit(root, "reconfigure")


def test_turning_a_check_off_through_its_own_key_is_an_error(tmp_path: Path) -> None:
    """Removing the name from `checks.enabled` was sealed; switching the same check off
    one line lower was not, and the sealed list still read as untouched."""
    base = _config_repo(tmp_path, "[checks.external_links]\nenabled = true\n")
    _reconfigure(tmp_path, "[checks.external_links]\nenabled = false\n")

    assert "diff-integrity/setting-weakened" in _codes(tmp_path, base)


def test_widening_a_threshold_is_an_error(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    _reconfigure(tmp_path, "[overrides]\nmtime_drift_days = 3650\n")

    assert "diff-integrity/setting-weakened" in _codes(tmp_path, base)


def test_narrowing_a_threshold_is_not(tmp_path: Path) -> None:
    """The seal is on asking less, not on touching the file."""
    base = _config_repo(tmp_path)
    _reconfigure(tmp_path, "[overrides]\nmtime_drift_days = 3\n")

    assert "diff-integrity/setting-weakened" not in _codes(tmp_path, base)


def test_a_decision_record_accepts_a_widened_threshold(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    _write(
        tmp_path,
        "docs/decisions/slow-repo.md",
        "---\nid: slow-repo\ntitle: Slow repo\nstatus: stable\n---\n\n"
        "# Slow repo\n\n## Decision\n\nWiden `mtime_drift_days`: this tree is archival.\n",
    )
    _reconfigure(tmp_path, "[overrides]\nmtime_drift_days = 3650\n")

    assert "diff-integrity/setting-weakened" not in _codes(tmp_path, base)


def test_removing_a_configured_rule_is_reported(tmp_path: Path) -> None:
    _repo(tmp_path)
    rule = (
        '[[checks.terminology_overload.rules]]\nterm = "coverage"\n'
        'explicit_phrases = ["source coverage"]\nsuggestion = "say which"\n'
    )
    _write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED + rule)
    base = _commit(tmp_path, "base")
    _write(tmp_path, "irminsul.toml", _CONFIG + _ENABLED)
    _commit(tmp_path, "drop the rule")

    # Its own code: the source-walk explanation and suggestion describe something else,
    # and a baseline entry or ignore comment for one must not hide the other.
    assert "diff-integrity/rules-narrowed" in _codes(tmp_path, base)


# --- CI: a step whose result is discarded ----------------------------------------


def _gated_repo(root: Path) -> str:
    _repo(root)
    _write(root, ".github/workflows/docs.yml", _workflow("pull_request", _GATE))
    return _commit(root, "gated workflow")


def _replace_workflow(root: Path, step: str, message: str) -> None:
    _write(root, ".github/workflows/docs.yml", _workflow("pull_request", step))
    _commit(root, message)


def test_continue_on_error_on_the_step_is_a_weakening(tmp_path: Path) -> None:
    """Every flag stays where it was and the step still runs; its exit code is thrown
    away, so counting flags read the gate as untouched."""
    base = _gated_repo(tmp_path)
    _replace_workflow(tmp_path, _GATE + "        continue-on-error: true\n", "ignore the result")

    assert _weakenings(tmp_path, base)


def test_continue_on_error_on_the_job_is_a_weakening(tmp_path: Path) -> None:
    base = _gated_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        "name: docs\n\non: pull_request\n\njobs:\n  docs:\n    runs-on: ubuntu-latest\n"
        "    continue-on-error: true\n    steps:\n      - uses: actions/checkout@v4\n"
        "        with:\n          fetch-depth: 0\n      - run: pip install irminsul\n" + _GATE,
    )
    _commit(tmp_path, "ignore the job")

    assert _weakenings(tmp_path, base)


def test_a_statically_false_condition_is_a_weakening(tmp_path: Path) -> None:
    base = _gated_repo(tmp_path)
    _replace_workflow(tmp_path, _GATE + "        if: false\n", "switch it off")

    assert _weakenings(tmp_path, base)


def test_an_ordinary_conditional_step_is_not(tmp_path: Path) -> None:
    """Only a provably false condition counts. Evaluating an expression would need the
    event, and guessing would report every conditional workflow in the world."""
    base = _gated_repo(tmp_path)
    _replace_workflow(
        tmp_path,
        _GATE + "        if: github.event_name == 'pull_request'\n",
        "add a condition",
    )

    assert _weakenings(tmp_path, base) == []


def test_discarding_the_exit_code_is_a_weakening(tmp_path: Path) -> None:
    base = _gated_repo(tmp_path)
    _replace_workflow(
        tmp_path,
        '      - run: irminsul check --strict --diff "origin/main" || true\n',
        "swallow the failure",
    )

    assert _weakenings(tmp_path, base)


def test_a_block_that_stops_erroring_out_is_a_weakening(tmp_path: Path) -> None:
    """Both halves together: errexit off *and* an exit that ignores the result."""
    base = _gated_repo(tmp_path)
    _replace_workflow(
        tmp_path,
        "      - run: |\n          set +e\n"
        '          irminsul check --strict --diff "origin/main"\n'
        "          exit 0\n",
        "stop erroring out",
    )

    assert _weakenings(tmp_path, base)


def test_turning_errexit_off_around_a_probe_is_not_a_weakening(tmp_path: Path) -> None:
    """`set +e` alone neutralises nothing: the step still exits with the last command's
    status, so a script that restores errexit and then gates still gates. Reporting it was
    a certain error on a script that had weakened nothing."""
    base = _gated_repo(tmp_path)
    _replace_workflow(
        tmp_path,
        "      - run: |\n          set +e\n          flaky-probe\n          set -e\n"
        '          irminsul check --strict --diff "origin/main"\n',
        "probe before the gate",
    )

    assert _weakenings(tmp_path, base) == []


def test_a_trailing_exit_zero_after_a_gate_is_not_a_weakening(tmp_path: Path) -> None:
    """GitHub runs `bash -eo pipefail`, so a failing gate aborts before the exit is
    reached. Only errexit being off as well makes that exit reachable."""
    base = _gated_repo(tmp_path)
    _replace_workflow(
        tmp_path,
        '      - run: |\n          irminsul check --strict --diff "origin/main"\n'
        "          echo done\n          exit 0\n",
        "tidy the script",
    )

    assert _weakenings(tmp_path, base) == []


def test_a_gate_commented_out_inside_a_block_is_a_weakening(tmp_path: Path) -> None:
    """Reading run steps from parsed YAML dropped the shell-comment stripping the raw-text
    scan did: `#` inside a block scalar is YAML content, so a commented-out gate still
    scored at full strength — the one-character bypass the comment rule exists to stop."""
    base = _gated_repo(tmp_path)
    _replace_workflow(
        tmp_path,
        '      - run: |\n          # irminsul check --strict --diff "origin/main"\n'
        "          echo skipping\n",
        "comment the gate out",
    )

    assert _weakenings(tmp_path, base)


def test_continue_on_error_on_an_action_step_is_a_weakening(tmp_path: Path) -> None:
    """The scaffolded workflows gate through `uses:`, so leaving the action path out of
    the switched-off test gave adopters none of this protection."""
    _repo(tmp_path)
    gate = (
        "      - uses: acme/irminsul@v1\n        with:\n"
        "          strict: true\n          diff: origin/main\n"
    )
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", gate))
    base = _commit(tmp_path, "action gate")
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _workflow("pull_request", "      - continue-on-error: true\n" + gate[6:]),
    )
    _commit(tmp_path, "ignore the action result")

    assert _weakenings(tmp_path, base)


def test_an_unchanged_gate_is_still_no_weakening(tmp_path: Path) -> None:
    """The reading of run steps moved from raw lines to parsed YAML, so the case that
    must not move is a workflow edited in a way that changes nothing about the gate."""
    base = _gated_repo(tmp_path)
    _replace_workflow(tmp_path, _GATE + "        name: gate\n", "name the step")

    assert _weakenings(tmp_path, base) == []
