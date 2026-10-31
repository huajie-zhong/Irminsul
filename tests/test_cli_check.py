"""End-to-end tests for the wired-up `irminsul check` command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import cli_output

runner = CliRunner()


def test_check_good_fixture_exits_zero(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "0 errors" in result.stdout


def test_check_bad_frontmatter_exits_one_with_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exit_code == 1
    assert "[frontmatter/" in result.stdout
    assert "missing frontmatter" in result.stdout


def test_check_bad_globs_exits_one_and_names_pattern(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-globs")
    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exit_code == 1
    assert "[globs/" in result.stdout
    assert "app/missing/*.py" in result.stdout


def test_check_format_json_produces_valid_json(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["version"] == 1
    assert isinstance(data["findings"], list)
    assert data["summary"]["errors"] == 0


def test_check_format_json_exit_one_on_errors(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["summary"]["errors"] > 0
    assert any(f["check"] == "frontmatter" for f in data["findings"])


def test_check_format_json_finding_schema(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(repo)])
    data = json.loads(result.stdout)
    for finding in data["findings"]:
        assert "check" in finding
        assert "code" in finding
        assert "severity" in finding
        assert "message" in finding
        assert "path" in finding
        assert "doc_id" in finding
        assert "line" in finding
        assert "suggestion" in finding
        assert "category" not in finding
        assert finding["code"].startswith(f"{finding['check']}/")


def test_check_format_unknown_exits_two(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--format", "xml", "--path", str(repo)])
    assert result.exit_code == 2


def test_check_unknown_check_name_exits_two_with_suggestion(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-check-name")
    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exit_code == 2
    assert "checks.enabled" in result.output
    assert "'unqueness'" in result.output
    assert "did you mean 'uniqueness'?" in result.output


def test_check_names_checks_enabled_when_the_split_lists_remain(tmp_path: Path) -> None:
    """A config from before the class model names the key that replaced its lists."""
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "moved"\n[paths]\ndocs_root = "docs"\n'
        '[checks]\nsoft_deterministic = ["retired-references"]\n',
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()

    result = runner.invoke(app, ["check", "--path", str(tmp_path)])

    assert result.exit_code == 2
    assert "checks.soft_deterministic no longer exist" in result.output
    assert "checks.enabled" in result.output


def test_check_good_fixture_config_still_loads(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout


def test_check_configured_runs_configured_soft_checks(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exit_code == 1, result.stdout
    assert "[supersession/" in result.stdout


def test_check_fails_on_retired_references_by_default(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The dogfood step in CI does not fail on hints. It is a hard check emitting
    errors so the gate actually fails."""
    repo = fixture_repo("hard-retired-references")

    result = runner.invoke(app, ["check", "--path", str(repo)])

    assert result.exit_code == 1, result.stdout
    assert "[retired-references/" in result.stdout
    assert "demo publish" in result.stdout
    assert "0001-retire-publish.md" in result.stdout


def test_hints_block_only_under_fail_on_hint(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    doc = repo / "docs" / "components" / "composer.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nBatching runs through `batch_all()`.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "[code-references/unknown-symbol]" in result.stdout

    widened = runner.invoke(app, ["check", "--fail-on", "hint", "--path", str(repo)])
    assert widened.exit_code == 1


def test_check_only_runs_a_check_that_is_not_enabled(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-boundary")
    (repo / "irminsul.toml").write_text(
        (repo / "irminsul.toml").read_text(encoding="utf-8") + '[checks]\nenabled = ["links"]\n',
        encoding="utf-8",
    )
    plain = runner.invoke(app, ["check", "--path", str(repo)])
    assert "[boundary/" not in plain.stdout

    result = runner.invoke(app, ["check", "--only", "boundary", "--path", str(repo)])
    assert result.exit_code == 1, result.stdout
    assert "[boundary/" in result.stdout


def test_check_only_lists_one_checks_findings(fixture_repo: Callable[[str], Path]) -> None:
    """`list orphans` and `list stale` were this, spelled as two more commands."""
    orphans = _check_json(fixture_repo("soft-orphans"), "--only", "orphans")
    assert orphans["findings"]
    assert {f["check"] for f in orphans["findings"]} == {"orphans"}

    # The copy has no git history, and `history-depth` judges the checks the run selected.
    stale = _check_json(fixture_repo("soft-stale-reaper"), "--only", "stale-reaper")
    assert "history-depth/no-history" in {f["code"] for f in stale["findings"]}
    assert {f["check"] for f in stale["findings"]} <= {"stale-reaper", "history-depth"}


def test_check_only_runs_the_named_checks_and_no_other(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    payload = _check_json(repo, "--only", "links", "--only", "orphans")
    assert {f["check"] for f in payload["findings"]} <= {"links", "orphans"}


def test_check_now_flag_rejects_garbage(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--now", "yesterday", "--path", str(repo)])
    assert result.exit_code == 2
    assert "yesterday" in cli_output(result)


def test_check_now_flag_threads_through_to_rfc_follow_through(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-rfc-follow-through")
    # With a 2025 "now" the stale-target RFC fires; with a 2020 "now" it does not.
    late = runner.invoke(
        app,
        ["check", "--now", "2025-01-01", "--path", str(repo)],
    )
    early = runner.invoke(
        app,
        ["check", "--now", "2020-01-01", "--path", str(repo)],
    )
    assert "target_decision_date" in late.stdout
    assert "target_decision_date" not in early.stdout


# --- machine-actionable findings: `data`, `fixable`, `fix_command` ---


def _check_json(repo: Path, *args: str) -> dict:
    import json

    result = runner.invoke(app, ["check", "--format", "json", "--path", str(repo), *args])
    return json.loads(result.stdout)


def test_check_json_all_findings_carry_data_and_fixable_keys(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    payload = _check_json(repo)
    assert payload["version"] == 1
    assert payload["findings"]
    for finding in payload["findings"]:
        assert "data" in finding
        assert "fixable" in finding
        assert isinstance(finding["fixable"], bool)
        if finding["data"] is not None:
            assert "problem" not in finding["data"]
            assert all(isinstance(v, str) for v in finding["data"].values())


def test_check_json_frontmatter_data_vocabulary(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    payload = _check_json(repo)
    by_path = {f["path"]: f["data"] for f in payload["findings"] if f["check"] == "frontmatter"}

    assert by_path["docs/components/missing-title.md"] == {
        "kind": "missing-field",
        "field": "title",
    }
    bad_status = by_path["docs/components/bad-status.md"]
    assert bad_status["kind"] == "invalid-value"
    assert bad_status["field"] == "status"
    assert bad_status["value"] == "retired"
    assert by_path["docs/components/no-frontmatter.md"] is None
    assert by_path["docs/components/renamed.md"] == {
        "field": "id",
        "value": "not-renamed",
        "expected": "renamed",
    }


def test_check_json_coverage_data_vocabulary(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-coverage")
    payload = _check_json(repo)
    coverage = [f for f in payload["findings"] if f["check"] == "coverage"]
    assert coverage
    assert coverage[0]["data"] == {
        "field": "recommended_tests",
    }

    # Declare a tests entry that points nowhere: tests-path-missing.
    doc = repo / "docs" / "components" / "thing.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "describes:", "recommended_tests:\n  - tests/test_thing.py\ndescribes:"
        ),
        encoding="utf-8",
    )
    payload = _check_json(repo)
    coverage = [f for f in payload["findings"] if f["check"] == "coverage"]
    assert coverage[0]["data"] == {
        "field": "recommended_tests",
        "value": "tests/test_thing.py",
    }


def test_check_json_links_data_vocabulary(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-links")
    linker = repo / "docs" / "components" / "linker.md"
    linker.write_text(
        linker.read_text(encoding="utf-8") + "\n- [bad anchor](#missing-section)\n",
        encoding="utf-8",
    )
    payload = _check_json(repo)
    links = [f for f in payload["findings"] if f["check"] == "links"]
    data_by_code: dict[str, list[dict]] = {}
    for f in links:
        data_by_code.setdefault(f["code"], []).append(f["data"])

    broken_targets = {d["target"] for d in data_by_code["links/broken-link"]}
    assert "does-not-exist.md" in broken_targets
    assert "nope.md#section" in broken_targets
    resolved = {d["resolved"] for d in data_by_code["links/broken-link"]}
    assert "docs/components/does-not-exist.md" in resolved

    anchors = {d["anchor"] for d in data_by_code["links/unknown-anchor"]}
    assert "missing-section" in anchors


def test_check_json_fixable_true_matches_fix_dry_run_plan(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    payload = _check_json(repo)
    supersession = [f for f in payload["findings"] if f["check"] == "supersession"]
    assert supersession
    for finding in supersession:
        assert finding["fixable"] is True
        assert finding["fix_command"] in (
            "irminsul fix --only supersession",
            "irminsul fix --only supersession --confirm",
        )

    # `irminsul fix --dry-run --confirm` really does plan these fixes.
    result = runner.invoke(app, ["fix", "--dry-run", "--confirm", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "planned" in result.output
    assert "status: deprecated" in result.output


def test_finding_records_take_fixability_from_the_graph_they_are_given(
    fixture_repo: Callable[[str], Path],
) -> None:
    from irminsul.checks.base import finding_records, fix_commands
    from irminsul.checks.pipeline import run_checks

    from .conftest import load_graph

    graph = load_graph(fixture_repo("soft-supersession"))
    findings = run_checks(graph, baseline=False).findings

    with_graph = finding_records(findings, graph)
    without_graph = finding_records(findings, None)

    assert any(record["fixable"] for record in with_graph)
    assert [record.get("fix_command") for record in with_graph] == fix_commands(findings, graph)
    assert not any(record["fixable"] for record in without_graph)


def test_check_json_fixable_false_without_fix_command(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    payload = _check_json(repo)
    frontmatter = [f for f in payload["findings"] if f["check"] == "frontmatter"]
    assert frontmatter
    for finding in frontmatter:
        assert finding["fixable"] is False
        assert "fix_command" not in finding


def test_check_json_fixable_false_for_unfixable_finding_of_fixing_check(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A check that implements fixes() must not over-claim: supersession
    errors (unknown doc id) have no automatic fix and stay fixable: false."""
    repo = fixture_repo("soft-supersession")
    ghost = repo / "docs" / "components" / "ghost-superseder.md"
    ghost.write_text(
        "---\n"
        "id: ghost-superseder\n"
        "title: Ghost Superseder\n"
        ""
        "status: stable\n"
        "supersedes:\n"
        "  - no-such-doc\n"
        "---\n\n"
        "# Ghost Superseder\n\n"
        "Supersedes a doc that does not exist.\n",
        encoding="utf-8",
    )
    payload = _check_json(repo)
    errors = [f for f in payload["findings"] if f["code"] == "supersession/unknown-supersedes"]
    assert errors
    for finding in errors:
        assert finding["fixable"] is False
        assert "fix_command" not in finding


def _run(command: str, repo: Path):
    """Invoke an emitted `fix_command` verbatim, scoped to `repo`."""
    assert command.startswith("irminsul ")
    return runner.invoke(app, [*command.split()[1:], "--path", str(repo)])


def test_fix_command_is_runnable_for_a_check_that_is_not_enabled(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A finding from a check that `--only` ran, outside `checks.enabled`, must still
    carry a command that plans its fix, because `fix --only` selects it the same way."""
    repo = fixture_repo("soft-supersession")
    toml = repo / "irminsul.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('    "supersession",\n', ""),
        encoding="utf-8",
    )

    payload = _check_json(repo, "--only", "supersession")
    fixable = [f for f in payload["findings"] if f["check"] == "supersession" and f["fixable"]]
    assert fixable
    command = fixable[0]["fix_command"]
    assert command.startswith("irminsul fix --only supersession")

    result = _run(command, repo)
    assert result.exit_code == 0, result.output
    assert "docs/components/old-system.md" in result.output
    assert "updated 1 file(s)" in result.output
    # A live run reports the file it wrote, so assert the remediation on disk.
    old_doc = repo / "docs" / "components" / "old-system.md"
    assert "status: deprecated" in old_doc.read_text(encoding="utf-8")


def test_fix_command_carries_confirm_for_confirm_gated_checks(
    fixture_repo: Callable[[str], Path],
) -> None:
    """rfc-follow-through's fixes are all `requires_confirm`, so the advertised
    command must include `--confirm` or it writes nothing."""
    repo = fixture_repo("soft-rfc-follow-through")
    payload = _check_json(repo)
    fixable = [
        f for f in payload["findings"] if f["check"] == "rfc-follow-through" and f["fixable"]
    ]
    assert fixable
    command = fixable[0]["fix_command"]
    assert command == "irminsul fix --only rfc-follow-through --confirm"

    result = _run(command, repo)
    assert result.exit_code == 0, result.output
    assert "held" not in result.output
    rfc = repo / "docs" / "rfcs" / "0002-accepted-bad-status.md"
    assert "status: stable" in rfc.read_text(encoding="utf-8")


def test_unfixable_rfc_finding_sharing_a_doc_with_a_fixable_one(
    fixture_repo: Callable[[str], Path],
) -> None:
    """An accepted RFC that is both `status: draft` and has a dangling
    `resolved_by` emits one fixable finding and one that has no fix. The
    dangling-resolved_by finding must not inherit the status fix's fixability
    — `irminsul fix` would not remediate it.
    """
    repo = fixture_repo("soft-rfc-follow-through")
    rfc = repo / "docs" / "rfcs" / "0003-accepted-broken-link.md"
    rfc.write_text(
        rfc.read_text(encoding="utf-8").replace("status: stable", "status: draft"),
        encoding="utf-8",
    )

    payload = _check_json(repo)
    doc = [
        f
        for f in payload["findings"]
        if f["check"] in ("rfc-follow-through", "rfc-lifecycle")
        and f["doc_id"] == "0003-accepted-broken-link"
    ]
    by_code = {f["code"]: f for f in doc}

    assert by_code["rfc-follow-through/status-not-stable"]["fixable"] is True
    assert by_code["rfc-lifecycle/dangling-resolved-by"]["fixable"] is False
    assert "fix_command" not in by_code["rfc-lifecycle/dangling-resolved-by"]

    # And the fix really does leave the dangling pointer behind.
    result = _run(by_code["rfc-follow-through/status-not-stable"]["fix_command"], repo)
    assert result.exit_code == 0, result.output
    after = _check_json(repo)
    still = [
        f
        for f in after["findings"]
        if f["doc_id"] == "0003-accepted-broken-link"
        and f["code"] == "rfc-lifecycle/dangling-resolved-by"
    ]
    assert still, "the unfixable finding must survive the fix that claimed it"


def test_supersession_unknown_id_finding_is_not_fixable_beside_a_fixable_one(
    fixture_repo: Callable[[str], Path],
) -> None:
    """Fixability is per finding: a doc carrying a fixable deprecation finding does not
    lend it to its own unfixable unknown-id finding."""
    repo = fixture_repo("soft-supersession")
    components = repo / "docs" / "components"
    new_system = components / "new-system.md"
    new_system.write_text(
        new_system.read_text(encoding="utf-8").replace(
            "supersedes: [old-system]", "supersedes: [old-system, no-such-doc]"
        ),
        encoding="utf-8",
    )
    (components / "newest-system.md").write_text(
        "---\n"
        "id: newest-system\n"
        "title: Newest System\n"
        "status: stable\n"
        "supersedes: [new-system]\n"
        "---\n\n"
        "# Newest System\n\n"
        "Supersedes new-system, which is not deprecated yet.\n",
        encoding="utf-8",
    )

    payload = _check_json(repo)
    on_new_system = [
        f
        for f in payload["findings"]
        if f["check"] == "supersession" and f["doc_id"] == "new-system"
    ]
    by_code = {f["code"]: f for f in on_new_system}

    assert by_code["supersession/status-not-deprecated"]["fixable"] is True
    assert by_code["supersession/unknown-supersedes"]["fixable"] is False
    assert "fix_command" not in by_code["supersession/unknown-supersedes"]


def test_check_runs_over_a_source_file_that_is_not_utf8(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    doc = repo / "docs" / "components" / "composer.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "  - app/composer.py\n", "  - app/composer.py\n  - app/latin1.py\n  - app/latin1.ts\n"
        ),
        encoding="utf-8",
    )
    for name in ("latin1.py", "latin1.ts"):
        (repo / "app" / name).write_bytes(b"x = '\xff\xfe'\n")
    result = runner.invoke(app, ["check", "--path", str(repo)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == 0, result.stdout
