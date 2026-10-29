"""The contract every entry point owes the adoption record, and the snapshot each
question is asked of.

These are regression tests for two confirmed defects found while reviewing the
cross-repository adoption design. They are expected to fail until the resolution/validation
refactor lands; each one names the property it is about rather than the code that breaks it,
so the fix is what makes them pass and nothing else has to be rewritten.

Two properties:

1. **A question about the base is answered with the base's configuration.** Ownership is a
   declaration plus the rule that accepts it, and the rule lives in `irminsul.toml`. Reading
   the base's documents through the head's rule lets one change alter what the base *meant*.

2. **A check may delegate reporting only where the caller guarantees the reporter runs.**
   `uniqueness` and `test-ownership` deliberately swallow `AdoptionError`, because the
   `adoption-record` pass reports it. Every path that runs those checks therefore has to run
   that pass, or an unreadable record reads as a tree with no debt and no problem.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import DECISIONS_INDEX, commit_all, gate_codes, git_init, write, write_config

runner = CliRunner()


_OWNER = (
    '---\nid: alpha\ntitle: "Alpha"\nstatus: stable\ndescribes:\n  - "src/a.py"\n'
    'owns_tests:\n  - "tests/helpers.py"\n---\n\n# Alpha\n\nIt does arithmetic.\n'
)


def _config(source_roots: str) -> str:
    return (
        'project_name = "ws"\n[paths]\ndocs_root = "docs"\n'
        f'source_roots = {source_roots}\ntest_roots = ["tests"]\n'
        '[checks]\nenabled = ["uniqueness", "test-ownership"]\n'
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository whose `tests/helpers.py` is governed as a test only by its location.

    Not `test_helpers.py`: a test-shaped *name* is rule 1 of `governed_as_test` and settles
    the question without consulting a single configured root, which is exactly the
    configuration dependence under test here.
    """
    root = tmp_path / "ws"
    root.mkdir()
    git_init(root, branch="main")
    write(root, "irminsul.toml", _config('["src"]'))
    write(root, "docs/decisions/INDEX.md", DECISIONS_INDEX)
    write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    write(root, "tests/helpers.py", "def helper() -> int:\n    return 1\n")
    commit_all(root, "base")
    return root


def _adopt(root: Path) -> None:
    result = runner.invoke(app, ["adoption", "init", "--path", str(root)])
    assert result.exit_code == 0, result.output
    commit_all(root, "adopt")


def _gate(root: Path, base: str) -> list[str]:
    """The error findings the generated pull-request workflow would report."""
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return sorted(
        f"{f['code']} {f.get('path') or ''}".strip()
        for f in json.loads(result.output)["findings"]
        if f["severity"] == "error"
    )


# ------------------------------------------- 1. the base is judged by the base's config


def test_widening_source_roots_cannot_revive_a_retired_exception(repo: Path) -> None:
    """Ownership is a declaration plus the rule that accepts it, and one change moves both.

    `tests/helpers.py` is not test-shaped by name, so it answers to the test policy only
    because it sits in a declared test root and outside every source root. At the base a
    document owns it through `owns_tests:`, which retires its adoption entry. The change
    then does two things that are individually unremarkable: it deletes the owner, and it
    adds `tests` to `source_roots` — a widening, which no rule reports.

    Adding the root flips the third clause of `governed_as_test`, so the base's declaration
    stops counting as ownership *when read through the head's config*. The file is unowned,
    the stale record still names it, and the exception is handed back. The revival rule
    exists to make the merge base supply the state the record failed to record, and it can
    only do that if the base is asked about with the base's own rules.
    """
    _adopt(repo)
    write(repo, "docs/components/alpha.md", _OWNER)
    base = commit_all(repo, "own the helper, record left stale")

    (repo / "docs/components/alpha.md").unlink()
    write(repo, "irminsul.toml", _config('["src", "tests"]'))
    commit_all(repo, "widen source_roots and drop the owner")

    errors = _gate(repo, base)

    # Both halves of the same document retire an exception, and both come back when it is
    # deleted. The `describes:` half is caught, because `owners()` needs no rule from the
    # config to decide a glob matched. Asserting it too keeps the contrast in the test: a
    # run that exits 1 on the second line is not evidence about the first.
    assert "diff-integrity/adoption-exception-revived src/a.py" in errors
    assert "diff-integrity/adoption-exception-revived tests/helpers.py" in errors


def test_a_base_whose_config_does_not_load_is_not_judged_by_the_head_s_rules(
    repo: Path,
) -> None:
    """The fallback the other direction, and the one that predates the rule above.

    `diff-integrity` reads the configuration at the merge base and falls back to the
    change's own when it will not load, reporting a warning. For most of what the seal does
    that is a reasonable degradation. For the adoption record it is the defect one test up,
    reached through a different door: the base's ownership rules are *unknown*, so judging
    them by the head's is guessing, and a warning is not enough when the answer decides
    whether an exception retired.

    Reachable only from a base that committed a configuration that does not load, which
    fails its own run with exit 2 — so in a repository whose check is required this state
    cannot be merged. That is a repository setting, not something this tool enforces, so the
    tool says what it cannot decide rather than relying on it.
    """
    _adopt(repo)
    write(repo, "docs/components/alpha.md", _OWNER)
    commit_all(repo, "own the helper, record left stale")
    write(repo, "irminsul.toml", "project_name = 'ws'\nthis is not toml\n")
    base = commit_all(repo, "commit a config that does not load")

    (repo / "docs/components/alpha.md").unlink()
    write(repo, "irminsul.toml", _config('["src", "tests"]'))
    commit_all(repo, "restore a config, widen it, and drop the owner")

    errors = _gate(repo, base)

    assert any("adoption-base-unreadable" in error for error in errors), errors


# ---------------------------------- 2. no entry point may report a clean unreadable record


@pytest.fixture
def unreadable(tmp_path: Path) -> Path:
    """A repository whose adoption record exists, does not load, and hides a real finding.

    The ownership checks read the record, find nothing readable, and say nothing — by
    design, on the understanding that the `adoption-record` pass reports it. So every entry
    point that runs those checks has to run that pass.

    The corruption is not inert. A readable record turns off the covered-directory guess,
    which makes the ownership rule *stricter*: `src/new.py` is unowned, unrecorded, and an
    error. An unreadable one falls back to the progressive rule, no document claims
    anything under `src`, the directory is uncovered, and the file is excused. So the
    difference between running the pass and not running it is the difference between a
    blocked run and a silent one — not between two wordings of the same verdict.
    """
    root = tmp_path / "quiet"
    root.mkdir()
    git_init(root, branch="main")
    write_config(root, project_name="q", source_roots=["src"], enabled=["uniqueness"])
    write(root, "docs/decisions/INDEX.md", DECISIONS_INDEX)
    write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    commit_all(root, "base")
    _adopt(root)

    write(root, "src/new.py", "def n() -> int:\n    return 1\n")
    (root / ".irminsul-adoption.json").write_text(
        '{"version": 1, "unowned": 7}\n', encoding="utf-8"
    )
    commit_all(root, "add a file and corrupt the record")
    return root


def _codes_from_cli(root: Path) -> set[str]:
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root)])
    return {f["code"] for f in json.loads(result.output)["findings"]}


def _codes_from_mcp(root: Path) -> set[str]:
    from irminsul.config import load
    from irminsul.mcp_server import check_json

    config = load(root / "irminsul.toml")
    return {f["code"] for f in json.loads(check_json(root, config))["findings"]}


def _codes_from_context(root: Path) -> set[str]:
    """Context reports a verdict and counts rather than a code list, so this drives it for the
    mandatory-pass assertion and the verdict is asserted on its own below."""
    from irminsul.config import load
    from irminsul.context import build_context_report

    config = load(root / "irminsul.toml")
    build_context_report(root, config, after_edit=True)
    return set()


@pytest.mark.parametrize(
    "entry_point",
    [
        pytest.param(_codes_from_cli, id="cli-check"),
        pytest.param(gate_codes, id="change-gates"),
        pytest.param(_codes_from_mcp, id="mcp-check-json"),
    ],
)
def test_every_entry_point_reports_an_unreadable_record(entry_point, unreadable: Path) -> None:
    """The pass that reports it runs outside `checks.enabled` precisely so no configuration
    can omit it. A caller that assembles its own run omits it just as effectively."""
    assert "adoption-record/unreadable" in entry_point(unreadable)


def test_context_after_edit_does_not_report_a_corrupt_record_as_a_clean_tree(
    unreadable: Path,
) -> None:
    """`--after-edit` is the step the root `AGENTS.md` loop puts between editing and
    committing, and its verdict is what an agent acts on. Asserted through the report's own
    verdict rather than a finding list: whether the command fails is the behaviour that
    matters."""
    from irminsul.config import load
    from irminsul.context import build_context_report, context_report_should_fail

    config = load(unreadable / "irminsul.toml")
    report = build_context_report(unreadable, config, after_edit=True)

    assert context_report_should_fail(report) is True


def test_no_entry_point_can_skip_a_pass(unreadable: Path, monkeypatch) -> None:
    """The structural half of the contract, and the half that does not rot.

    The tests above prove today's passes reach today's entry points, which is a statement
    about two lists that both grow. This one replaces every pass in `PASSES` with a sentinel
    and asserts each entry point fired all of them — so a pass added later is covered without
    touching this file, and an entry point that goes back to assembling its own run fails here
    rather than in six months on somebody's repository.
    """
    from irminsul.checks import pipeline

    fired: set[str] = set()

    def sentinel(name: str):
        def run(self, graph, selected):
            fired.add(name)
            return []

        return run

    names = list(pipeline.PASSES)
    assert names, "no passes declared, so this proves nothing"
    for name, cls in pipeline.PASSES.items():
        monkeypatch.setattr(cls, "run", sentinel(name), raising=True)

    for entry_point in (
        _codes_from_cli,
        gate_codes,
        _codes_from_mcp,
        _codes_from_context,
    ):
        fired.clear()
        entry_point(unreadable)
        assert fired == set(names), f"{entry_point.__name__} skipped {set(names) - fired}"


def test_the_corruption_is_load_bearing(unreadable: Path) -> None:
    """Guards the fixture itself, in both directions.

    If a later change made the progressive fallback report `src/new.py` anyway, the tests
    above would pass while proving nothing — an entry point that reports *something* is not
    the bug. So: with a well-formed record the file is an error, and corrupting the record
    takes that error away. The hidden finding is shown to exist before it is shown to be
    hidden.
    """
    record = unreadable / ".irminsul-adoption.json"
    record.write_text(json.dumps({"version": 1, "unowned": ["src/a.py"]}) + "\n", encoding="utf-8")
    assert "uniqueness/undocumented-file" in _codes_from_mcp(unreadable)

    record.write_text('{"version": 1, "unowned": 7}\n', encoding="utf-8")
    assert "uniqueness/undocumented-file" not in _codes_from_mcp(unreadable)


#: A check's `run` called on an instance made in place, `Check().run(` or
#: `REGISTRY[name]().run(`, or on one held in a variable, `check.run(graph)`.
_DIRECT_RUN = re.compile(r"\(\)\.run\(|\b\w+\.run\(\s*\w*graph\b")


def test_only_known_runners_assemble_a_check_run() -> None:
    """The list of entry points above is hand-written, and that is what went wrong.

    `status` was a fourth runner nobody had added to it, so it reported zero errors for a
    record `check` fails on — the same bug as the MCP server and `context`, found by a
    reviewer rather than by the test that exists to find it. A test over a list cannot
    notice a runner missing from the list.

    So this one reads the source. Every module that touches the check registry is either
    routed through the shared run or named here with the reason it is not a verdict, and a
    new one fails until somebody decides which it is. A plain substring, not a pattern: the
    first attempt used a lookbehind to exclude `LANGUAGE_REGISTRY`, matched nothing at all,
    and passed on an empty set — a guard that reports success for finding nothing is worse
    than no guard, so this one proves it read something before its silence means anything.

    The registry is not the only way in: `ClaimAnchorCheck().run(graph)` builds a run from
    one imported class without naming it, which is how the anchor report and two lifecycle
    blockers came to skip classes, ignore comments and the baseline. So a direct call to a
    check's `run` is a second needle, and only the pipeline may hold one.
    """
    root = Path(__file__).resolve().parents[1] / "src" / "irminsul"
    found = set()
    direct_runs = set()
    for path in root.rglob("*.py"):
        # The language profiles are data, not checks, and share the word.
        text = path.read_text(encoding="utf-8").replace("LANGUAGE_REGISTRY", "")
        relative = path.relative_to(root).as_posix()
        if "REGISTRY" in text:
            found.add(relative)
        if _DIRECT_RUN.search(text):
            direct_runs.add(relative)

    accounted = {
        # The registry itself, and the shared run that owns `PASSES`.
        "checks/__init__.py",
        "checks/pipeline.py",
        # Routed through the shared run, and `fix` reads each selected check's `fixes`.
        "cli.py",
        # Not verdicts, and deliberately so:
        # `checks/base.py` resolves a class to explain one finding it was handed.
        "checks/base.py",
        # `config.py` validates the names in `checks.enabled` against it and runs no check.
        "config.py",
        # `baseline.py` asks whether a finding's check is registered, which decides only
        # whether a baseline may record the finding; it runs no check.
        "baseline.py",
        # `orient` reports only `time`-class findings from the checks that produce them. The
        # mandatory passes produce certain findings, which it neither asks for nor reports;
        # including them would make orientation fail runs.
        "orient.py",
    }

    # Shown to have read something before its silence is taken for agreement.
    assert "checks/pipeline.py" in found, f"the scan found nothing: {sorted(found)}"
    assert "checks/pipeline.py" in direct_runs, (
        f"the run needle matched nothing, so its silence proves nothing: {sorted(direct_runs)}"
    )
    assert direct_runs == {"checks/pipeline.py"}, (
        "these modules call a check's `run` themselves, which skips classes, ignore comments "
        f"and the baseline: {sorted(direct_runs - {'checks/pipeline.py'})}. Use "
        "`checks.pipeline.run_checks` for a verdict, or `run_check` for one check's own items."
    )
    assert accounted <= found, (
        "these are listed here but no longer touch the registry; drop them so the list keeps "
        f"meaning something: {sorted(accounted - found)}"
    )
    assert found <= accounted, (
        f"these modules assemble a check run and are unaccounted for: {sorted(found - accounted)}."
        " Route each through `checks.pipeline.run_checks` if it reaches a verdict, or"
        " add it above with the reason it does not."
    )
