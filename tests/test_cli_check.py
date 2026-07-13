"""End-to-end tests for the wired-up `irminsul check` command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def test_check_good_fixture_exits_zero(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "0 errors" in result.stdout


def test_check_bad_frontmatter_exits_one_with_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(repo)])
    assert result.exit_code == 1
    assert "[frontmatter]" in result.stdout
    assert "missing frontmatter" in result.stdout


def test_check_bad_globs_exits_one_and_names_pattern(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-globs")
    result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(repo)])
    assert result.exit_code == 1
    assert "[globs]" in result.stdout
    assert "app/missing/*.py" in result.stdout


def test_check_rejects_removed_advisory_profile(fixture_repo: Callable[[str], Path]) -> None:
    """The advisory profile died with the LLM check subsystem; Typer must
    reject it as an invalid choice rather than silently running nothing."""
    repo = fixture_repo("good")

    result = runner.invoke(app, ["check", "--profile", "advisory", "--path", str(repo)])

    assert result.exit_code != 0
    assert "advisory" in result.output
    assert "Invalid value" in result.output


def test_check_format_json_produces_valid_json(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("good")
    result = runner.invoke(
        app, ["check", "--profile", "hard", "--format", "json", "--path", str(repo)]
    )
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
    result = runner.invoke(
        app, ["check", "--profile", "hard", "--format", "json", "--path", str(repo)]
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["summary"]["errors"] > 0
    assert any(f["check"] == "frontmatter" for f in data["findings"])


def test_check_format_json_finding_schema(
    fixture_repo: Callable[[str], Path],
) -> None:
    import json

    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(
        app, ["check", "--profile", "hard", "--format", "json", "--path", str(repo)]
    )
    data = json.loads(result.stdout)
    for finding in data["findings"]:
        assert "check" in finding
        assert "severity" in finding
        assert "message" in finding
        assert "path" in finding
        assert "doc_id" in finding
        assert "line" in finding
        assert "suggestion" in finding
        assert "category" in finding


def test_check_format_unknown_exits_two(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--format", "xml", "--path", str(repo)])
    assert result.exit_code == 2


def test_check_configured_runs_configured_soft_checks(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    result = runner.invoke(app, ["check", "--profile", "configured", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "[supersession]" in result.stdout


def test_check_strict_fails_on_warnings(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    result = runner.invoke(
        app, ["check", "--profile", "configured", "--strict", "--path", str(repo)]
    )
    assert result.exit_code == 1
    assert "[supersession]" in result.stdout


def test_check_strict_does_not_enable_soft_checks(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    result = runner.invoke(app, ["check", "--profile", "hard", "--strict", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "[supersession]" not in result.stdout


def test_check_all_available_runs_unconfigured_deterministic_checks(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-boundary")
    result = runner.invoke(app, ["check", "--profile", "all-available", "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    assert "[boundary]" in result.stdout


def test_check_now_flag_rejects_garbage(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(
        app, ["check", "--profile", "hard", "--now", "yesterday", "--path", str(repo)]
    )
    assert result.exit_code == 2
    assert "yesterday" in result.stdout


def test_check_now_flag_threads_through_to_rfc_resolution(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-rfc-resolution")
    # With a 2025 "now" the stale-target RFC fires; with a 2020 "now" it does not.
    late = runner.invoke(
        app,
        ["check", "--profile", "configured", "--now", "2025-01-01", "--path", str(repo)],
    )
    early = runner.invoke(
        app,
        ["check", "--profile", "configured", "--now", "2020-01-01", "--path", str(repo)],
    )
    assert "target_decision_date" in late.stdout
    assert "target_decision_date" not in early.stdout


def test_check_base_ref_requires_head_ref(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(app, ["check", "--base-ref", "HEAD~1", "--path", str(repo)])
    assert result.exit_code == 2
    assert "must be provided together" in result.stdout


def test_check_base_head_refs_alias_unified_co_change(tmp_path: Path) -> None:
    from git import Repo

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo = Repo.init(repo_root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")

    (repo_root / "app").mkdir()
    (repo_root / "app" / "thing.py").write_text("x = 1\n", encoding="utf-8")
    docs = repo_root / "docs" / "20-components"
    docs.mkdir(parents=True)
    (docs / "thing.md").write_text(
        "---\nid: thing\ntitle: Thing\naudience: explanation\ntier: 3\n"
        "status: stable\ndescribes:\n  - app/thing.py\n---\n\n# Thing\n",
        encoding="utf-8",
    )
    (repo_root / "irminsul.toml").write_text(
        'project_name = "diff-aware"\n'
        '[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nsoft_deterministic = ["mtime-drift"]\n',
        encoding="utf-8",
    )
    repo.index.add(["app/thing.py", "docs/20-components/thing.md", "irminsul.toml"])
    base = repo.index.commit("seed").hexsha
    (repo_root / "app" / "thing.py").write_text("x = 2\n", encoding="utf-8")
    repo.index.add(["app/thing.py"])
    repo.index.commit("change source only")
    repo.close()

    result = runner.invoke(
        app,
        [
            "check",
            "--profile",
            "configured",
            "--base-ref",
            base,
            "--head-ref",
            "HEAD",
            "--path",
            str(repo_root),
        ],
    )
    # --base-ref/--head-ref is the two-flag spelling of --diff: the unified
    # co-change signal fires instead of the old mtime-drift diff finding.
    assert "co-change" in result.stdout
    assert "changed in the diff but the doc did not" in result.stdout


def _init_repo(root: Path) -> None:
    from git import Repo

    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    repo.git.add("-A")
    repo.index.commit("seed")
    repo.close()


def test_check_unresolvable_base_ref_warns_and_still_reports_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A ref the repo cannot resolve (e.g. a shallow CI clone that never fetched
    the base sha) must not swallow the run: warn, skip co-change, keep checking."""
    repo = fixture_repo("bad-frontmatter")
    _init_repo(repo)

    result = runner.invoke(
        app,
        [
            "check",
            "--profile",
            "hard",
            "--base-ref",
            "no-such-ref",
            "--head-ref",
            "HEAD",
            "--path",
            str(repo),
        ],
    )

    assert "skipping diff-aware checks" in result.output
    # Exit code is driven by the findings, not by the failed ref resolution.
    assert result.exit_code == 1
    assert "[frontmatter]" in result.stdout
    assert "missing frontmatter" in result.stdout


def test_check_unresolvable_base_ref_still_exits_zero_on_a_clean_repo(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("good")
    _init_repo(repo)

    result = runner.invoke(
        app,
        [
            "check",
            "--profile",
            "hard",
            "--base-ref",
            "no-such-ref",
            "--head-ref",
            "HEAD",
            "--path",
            str(repo),
        ],
    )

    assert "skipping diff-aware checks" in result.output
    assert result.exit_code == 0, result.output
    assert "0 errors" in result.stdout


def test_check_empty_base_ref_exits_2(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    result = runner.invoke(
        app, ["check", "--base-ref", "", "--head-ref", "HEAD", "--path", str(repo)]
    )
    assert result.exit_code == 2
    assert "empty value" in result.output


# --- machine-actionable findings: `data`, `fixable`, `fix_command` ---


def _check_json(repo: Path, *args: str) -> dict:
    import json

    result = runner.invoke(app, ["check", "--format", "json", "--path", str(repo), *args])
    return json.loads(result.stdout)


def test_check_json_all_findings_carry_data_and_fixable_keys(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    payload = _check_json(repo, "--profile", "hard")
    assert payload["version"] == 1
    assert payload["findings"]
    for finding in payload["findings"]:
        assert "data" in finding
        assert "fixable" in finding
        assert isinstance(finding["fixable"], bool)
        if finding["data"] is not None:
            assert "problem" in finding["data"]
            assert all(isinstance(v, str) for v in finding["data"].values())


def test_check_json_frontmatter_data_vocabulary(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    payload = _check_json(repo, "--profile", "hard")
    by_path = {f["path"]: f["data"] for f in payload["findings"] if f["check"] == "frontmatter"}

    assert by_path["docs/20-components/missing-audience.md"] == {
        "problem": "missing-field",
        "field": "audience",
    }
    bad_tier = by_path["docs/20-components/bad-tier.md"]
    assert bad_tier["problem"] == "invalid-value"
    assert bad_tier["field"] == "tier"
    assert bad_tier["value"] == "99"
    assert by_path["docs/20-components/no-frontmatter.md"] == {"problem": "missing-frontmatter"}
    assert by_path["docs/20-components/renamed.md"] == {
        "problem": "id-mismatch",
        "field": "id",
        "value": "not-renamed",
        "expected": "renamed",
    }


def test_check_json_coverage_data_vocabulary(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-coverage")
    payload = _check_json(repo, "--profile", "hard")
    coverage = [f for f in payload["findings"] if f["check"] == "coverage"]
    assert coverage
    assert coverage[0]["data"] == {"problem": "missing-tests-entry", "field": "tests"}

    # Declare a tests entry that points nowhere: tests-path-missing.
    doc = repo / "docs" / "20-components" / "thing.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "describes:", "tests:\n  - tests/test_thing.py\ndescribes:"
        ),
        encoding="utf-8",
    )
    payload = _check_json(repo, "--profile", "hard")
    coverage = [f for f in payload["findings"] if f["check"] == "coverage"]
    assert coverage[0]["data"] == {
        "problem": "tests-path-missing",
        "field": "tests",
        "value": "tests/test_thing.py",
    }


def test_check_json_links_data_vocabulary(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-links")
    linker = repo / "docs" / "20-components" / "linker.md"
    linker.write_text(
        linker.read_text(encoding="utf-8") + "\n- [bad anchor](#missing-section)\n",
        encoding="utf-8",
    )
    payload = _check_json(repo, "--profile", "hard")
    links = [f for f in payload["findings"] if f["check"] == "links"]
    data_by_problem: dict[str, list[dict]] = {}
    for f in links:
        data_by_problem.setdefault(f["data"]["problem"], []).append(f["data"])

    broken_targets = {d["target"] for d in data_by_problem["broken-link"]}
    assert "does-not-exist.md" in broken_targets
    assert "nope.md#section" in broken_targets
    resolved = {d["resolved"] for d in data_by_problem["broken-link"]}
    assert "docs/20-components/does-not-exist.md" in resolved

    anchors = {d["anchor"] for d in data_by_problem["unknown-anchor"]}
    assert "missing-section" in anchors


def test_check_json_fixable_true_matches_fix_dry_run_plan(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-supersession")
    payload = _check_json(repo, "--profile", "configured")
    supersession = [f for f in payload["findings"] if f["check"] == "supersession"]
    assert supersession
    for finding in supersession:
        assert finding["fixable"] is True
        assert finding["fix_command"] == "irminsul fix --profile configured --check supersession"

    # `irminsul fix --dry-run` really does plan these fixes.
    result = runner.invoke(app, ["fix", "--dry-run", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "planned" in result.output
    assert "status: deprecated" in result.output


def test_check_json_fixable_false_without_fix_command(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("bad-frontmatter")
    payload = _check_json(repo, "--profile", "hard")
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
    ghost = repo / "docs" / "20-components" / "ghost-superseder.md"
    ghost.write_text(
        "---\n"
        "id: ghost-superseder\n"
        "title: Ghost Superseder\n"
        "audience: explanation\n"
        "tier: 2\n"
        "status: stable\n"
        "supersedes:\n"
        "  - no-such-doc\n"
        "---\n\n"
        "# Ghost Superseder\n\n"
        "Supersedes a doc that does not exist.\n",
        encoding="utf-8",
    )
    payload = _check_json(repo, "--profile", "configured")
    errors = [
        f for f in payload["findings"] if f["check"] == "supersession" and f["severity"] == "error"
    ]
    assert errors
    for finding in errors:
        assert finding["fixable"] is False
        assert "fix_command" not in finding


def _run(command: str, repo: Path):
    """Invoke an emitted `fix_command` verbatim, scoped to `repo`."""
    assert command.startswith("irminsul ")
    return runner.invoke(app, [*command.split()[1:], "--path", str(repo)])


def test_fix_command_is_runnable_under_the_profile_that_reported_it(
    fixture_repo: Callable[[str], Path],
) -> None:
    """`fixable` must respect the profile gating `irminsul fix` enforces.

    A check active only under `all-available` (not in the repo's configured
    soft set) must still emit a command that actually plans the fix, rather
    than one that no-ops with "not active under profile".
    """
    repo = fixture_repo("soft-supersession")
    toml = repo / "irminsul.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace(
            'soft_deterministic = ["supersession"]', "soft_deterministic = []"
        ),
        encoding="utf-8",
    )

    payload = _check_json(repo, "--profile", "all-available")
    fixable = [f for f in payload["findings"] if f["check"] == "supersession" and f["fixable"]]
    assert fixable
    command = fixable[0]["fix_command"]
    assert command == "irminsul fix --profile all-available --check supersession"

    result = _run(command, repo)
    assert result.exit_code == 0, result.output
    assert "not active under profile" not in result.output
    assert "status: deprecated" in result.output
    assert "updated 1 file(s)" in result.output


def test_fix_command_carries_confirm_for_confirm_gated_checks(
    fixture_repo: Callable[[str], Path],
) -> None:
    """rfc-resolution's fixes are all `requires_confirm`, so the advertised
    command must include `--confirm` or it writes nothing."""
    repo = fixture_repo("soft-rfc-resolution")
    payload = _check_json(repo, "--profile", "configured")
    fixable = [f for f in payload["findings"] if f["check"] == "rfc-resolution" and f["fixable"]]
    assert fixable
    command = fixable[0]["fix_command"]
    assert command == "irminsul fix --profile configured --check rfc-resolution --confirm"

    result = _run(command, repo)
    assert result.exit_code == 0, result.output
    assert "held" not in result.output
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0002-accepted-bad-status.md"
    assert "status: stable" in rfc.read_text(encoding="utf-8")


def test_rfc_resolution_unfixable_finding_sharing_a_doc_with_a_fixable_one(
    fixture_repo: Callable[[str], Path],
) -> None:
    """An accepted RFC that is both `status: draft` and has a dangling
    `resolved_by` emits one fixable finding and one that has no fix. The
    dangling-resolved_by finding must not inherit the status fix's fixability
    — `irminsul fix` would not remediate it.
    """
    repo = fixture_repo("soft-rfc-resolution")
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0003-accepted-broken-link.md"
    rfc.write_text(
        rfc.read_text(encoding="utf-8").replace("status: stable", "status: draft"),
        encoding="utf-8",
    )

    payload = _check_json(repo, "--profile", "configured")
    doc = [
        f
        for f in payload["findings"]
        if f["check"] == "rfc-resolution" and f["doc_id"] == "0003-accepted-broken-link"
    ]
    by_category = {f["category"]: f for f in doc}

    assert by_category["status-not-stable"]["fixable"] is True
    assert by_category["dangling-resolved-by"]["fixable"] is False
    assert "fix_command" not in by_category["dangling-resolved-by"]

    # And the fix really does leave the dangling pointer behind.
    result = _run(by_category["status-not-stable"]["fix_command"], repo)
    assert result.exit_code == 0, result.output
    after = _check_json(repo, "--profile", "configured")
    still = [
        f
        for f in after["findings"]
        if f["doc_id"] == "0003-accepted-broken-link" and f["category"] == "dangling-resolved-by"
    ]
    assert still, "the unfixable finding must survive the fix that claimed it"


def test_supersession_reverse_pointer_finding_is_not_fixable(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The reverse-pointer warning is stamped with the *superseding* doc's
    path/id and has no implemented fix. It must stay `fixable: false` even when
    that same doc carries fixable deprecation-metadata findings of its own.
    """
    repo = fixture_repo("soft-supersession")
    components = repo / "docs" / "20-components"
    (components / "ancient-system.md").write_text(
        "---\n"
        "id: ancient-system\n"
        "title: Ancient System\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: deprecated\n"
        "superseded_by: new-system\n"
        "---\n\n"
        "# Ancient System\n\n"
        "Claims new-system replaced it, but new-system does not list it in supersedes.\n",
        encoding="utf-8",
    )
    (components / "newest-system.md").write_text(
        "---\n"
        "id: newest-system\n"
        "title: Newest System\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "supersedes: [new-system]\n"
        "---\n\n"
        "# Newest System\n\n"
        "Supersedes new-system, whose own deprecation metadata is stale.\n",
        encoding="utf-8",
    )

    payload = _check_json(repo, "--profile", "configured")
    on_new_system = [
        f
        for f in payload["findings"]
        if f["check"] == "supersession" and f["doc_id"] == "new-system"
    ]
    by_category = {f["category"]: f for f in on_new_system}

    # new-system is itself superseded, so it has genuinely fixable findings...
    assert by_category["status-not-deprecated"]["fixable"] is True
    assert by_category["missing-superseded-by"]["fixable"] is True
    # ...but the reverse-pointer warning stamped on it has no fix.
    assert by_category["missing-supersedes"]["fixable"] is False
    assert "fix_command" not in by_category["missing-supersedes"]
