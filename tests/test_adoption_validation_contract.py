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
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_INDEX = "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n"

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


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@e.com", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository whose `tests/helpers.py` is governed as a test only by its location.

    Not `test_helpers.py`: a test-shaped *name* is rule 1 of `governed_as_test` and settles
    the question without consulting a single configured root, which is exactly the
    configuration dependence under test here.
    """
    root = tmp_path / "ws"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "irminsul.toml", _config('["src"]'))
    _write(root, "docs/decisions/INDEX.md", _INDEX)
    _write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    _write(root, "tests/helpers.py", "def helper() -> int:\n    return 1\n")
    _commit(root, "base")
    return root


def _adopt(root: Path) -> None:
    result = runner.invoke(app, ["check", "--init-adoption", "--path", str(root)])
    assert result.exit_code == 0, result.output
    _commit(root, "adopt")


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
    _write(repo, "docs/components/alpha.md", _OWNER)
    base = _commit(repo, "own the helper, record left stale")

    (repo / "docs/components/alpha.md").unlink()
    _write(repo, "irminsul.toml", _config('["src", "tests"]'))
    _commit(repo, "widen source_roots and drop the owner")

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
    _write(repo, "docs/components/alpha.md", _OWNER)
    _commit(repo, "own the helper, record left stale")
    _write(repo, "irminsul.toml", "project_name = 'ws'\nthis is not toml\n")
    base = _commit(repo, "commit a config that does not load")

    (repo / "docs/components/alpha.md").unlink()
    _write(repo, "irminsul.toml", _config('["src", "tests"]'))
    _commit(repo, "restore a config, widen it, and drop the owner")

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
    _git(root, "init", "-q", "-b", "main")
    _write(
        root,
        "irminsul.toml",
        'project_name = "q"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[checks]\nenabled = ["uniqueness"]\n',
    )
    _write(root, "docs/decisions/INDEX.md", _INDEX)
    _write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    _commit(root, "base")
    _adopt(root)

    _write(root, "src/new.py", "def n() -> int:\n    return 1\n")
    (root / ".irminsul-adoption.json").write_text(
        '{"version": 1, "unowned": 7}\n', encoding="utf-8"
    )
    _commit(root, "add a file and corrupt the record")
    return root


def _codes_from_cli(root: Path) -> set[str]:
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root)])
    return {f["code"] for f in json.loads(result.output)["findings"]}


def _codes_from_enabled_findings(root: Path) -> set[str]:
    from irminsul.checks.pipeline import enabled_findings
    from irminsul.config import load
    from irminsul.docgraph import build_graph

    config = load(root / "irminsul.toml")
    return {f.code for f in enabled_findings(build_graph(root, config))}


def _codes_from_mcp(root: Path) -> set[str]:
    from irminsul.config import load
    from irminsul.mcp_server import check_json

    config = load(root / "irminsul.toml")
    return {f["code"] for f in json.loads(check_json(root, config))["findings"]}


def _codes_from_status(root: Path) -> set[str]:
    """Status reports counts per check rather than codes, so the check name is what it can be
    asked for; the error count is asserted separately below."""
    from irminsul.config import load
    from irminsul.status import build_status_report

    config = load(root / "irminsul.toml")
    report = build_status_report(root, config)
    return {f"{check}/" for check in report.findings_by_check}


def _codes_from_context(root: Path) -> set[str]:
    """Context reports a verdict and counts rather than a code list, so this drives it for the
    mandatory-pass assertion and the verdict is asserted on its own below."""
    from irminsul.config import load
    from irminsul.context import build_context_report

    config = load(root / "irminsul.toml")
    build_context_report(root, config, changed=True, workflow="after-edit")
    return set()


@pytest.mark.parametrize(
    "entry_point",
    [
        pytest.param(_codes_from_cli, id="cli-check"),
        pytest.param(_codes_from_enabled_findings, id="enabled-findings"),
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
    """`--after-edit` is the step the agent protocol puts between editing and committing,
    and its verdict is what an agent acts on. Asserted through the report's own verdict
    rather than a finding list: whether the command fails is the behaviour that matters."""
    from irminsul.config import load
    from irminsul.context import build_context_report, context_report_should_fail

    config = load(unreadable / "irminsul.toml")
    report = build_context_report(unreadable, config, changed=True, workflow="after-edit")

    assert context_report_should_fail(report) is True


def test_no_entry_point_can_skip_a_mandatory_pass(unreadable: Path, monkeypatch) -> None:
    """The structural half of the contract, and the half that does not rot.

    The tests above prove today's mandatory passes reach today's entry points, which is a
    statement about two lists that both grow. This one replaces every pass in
    `MANDATORY_PASSES` with a sentinel and asserts each entry point fired all of them — so a
    pass added later is covered without touching this file, and an entry point that goes back
    to assembling its own run fails here rather than in six months on somebody's repository.
    """
    from irminsul.checks import pipeline

    fired: set[str] = set()

    def sentinel(name: str):
        def run(graph, selected):
            fired.add(name)
            return []

        return run

    names = [f"pass{index}" for index, _ in enumerate(pipeline.MANDATORY_PASSES)]
    assert names, "no mandatory passes declared, so this proves nothing"
    monkeypatch.setattr(
        pipeline, "MANDATORY_PASSES", tuple(sentinel(name) for name in names), raising=True
    )

    for entry_point in (
        _codes_from_cli,
        _codes_from_enabled_findings,
        _codes_from_mcp,
        _codes_from_context,
        _codes_from_status,
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
    """
    root = Path(__file__).resolve().parents[1] / "src" / "irminsul"
    found = set()
    for path in root.rglob("*.py"):
        # The language profiles are data, not checks, and share the word.
        text = path.read_text(encoding="utf-8").replace("LANGUAGE_REGISTRY", "")
        if "REGISTRY" in text:
            found.add(path.relative_to(root).as_posix())

    accounted = {
        # The registry itself, and the shared run that owns `MANDATORY_PASSES`.
        "checks/__init__.py",
        "checks/pipeline.py",
        # Routed through the shared run — each reaches a verdict, so each owes the whole run.
        "cli.py",
        "context.py",
        "mcp_server.py",
        "status.py",
        # Not verdicts, and deliberately so:
        # `checks/base.py` resolves a class to explain one finding it was handed.
        "checks/base.py",
        # `adoption_record.py` is one of the mandatory passes; it names the checks whose
        # exceptions the record grants and runs none of them.
        "checks/adoption_record.py",
        # `orient` reports only `time`-class findings from the checks that produce them. The
        # mandatory passes produce certain findings, which it neither asks for nor reports;
        # including them would make orientation fail runs.
        "orient.py",
    }

    # Shown to have read something before its silence is taken for agreement.
    assert "checks/pipeline.py" in found, f"the scan found nothing: {sorted(found)}"
    assert accounted <= found, (
        "these are listed here but no longer touch the registry; drop them so the list keeps "
        f"meaning something: {sorted(accounted - found)}"
    )
    assert found <= accounted, (
        f"these modules assemble a check run and are unaccounted for: {sorted(found - accounted)}."
        " Route each through `checks.pipeline.mandatory_findings` if it reaches a verdict, or"
        " add it above with the reason it does not."
    )


def test_status_does_not_call_a_corrupt_record_a_clean_repository(unreadable: Path) -> None:
    """`irminsul status` is a verdict — it prints an error count — and it assembled its own run
    from the registry, so it answered zero for a record `check` fails on. A fourth runner
    nobody had added to the list above, which is why that list is no longer the only guard."""
    from irminsul.config import load
    from irminsul.status import build_status_report

    report = build_status_report(unreadable, load(unreadable / "irminsul.toml"))

    assert report.errors >= 1
    assert "adoption-record" in report.findings_by_check
