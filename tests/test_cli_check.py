"""End-to-end tests for the wired-up `irminsul check` command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import irminsul.cli as cli
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


def test_check_advisory_runs_configured_llm_checks(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    (repo / "irminsul.toml").write_text(
        (repo / "irminsul.toml").read_text(encoding="utf-8")
        + '\n[checks]\nsoft_llm = ["overlap"]\n'
        + '\n[llm]\nprovider = "definitely-missing-provider"\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", "--profile", "advisory", "--path", str(repo)])

    assert result.exit_code == 0, result.stdout
    assert "[overlap]" in result.stdout
    assert "LLM check skipped" in result.stdout


def test_check_llm_footer_reports_api_calls_not_cache_hits(
    fixture_repo: Callable[[str], Path],
    monkeypatch,
) -> None:
    repo = fixture_repo("good")
    (repo / "irminsul.toml").write_text(
        (repo / "irminsul.toml").read_text(encoding="utf-8")
        + '\n[checks]\nsoft_llm = ["overlap"]\n'
        + '\n[llm]\nprovider = "openai"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    class OneCallLlmCheck:
        def __init__(self, *, llm_client):
            self.llm_client = llm_client

        def run(self, graph):
            from irminsul.llm.client import LlmRequest

            self.llm_client.complete(LlmRequest(system="system", user="user"))
            return []

    def fake_completion(**_kwargs):
        msg = SimpleNamespace(content='{"ok": true}')
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])

    monkeypatch.setitem(cli.LLM_REGISTRY, "overlap", OneCallLlmCheck)
    monkeypatch.setattr("litellm.completion", fake_completion)
    monkeypatch.setattr("litellm.completion_cost", lambda _raw: 0.01)

    result = runner.invoke(app, ["check", "--profile", "advisory", "--path", str(repo)])

    assert result.exit_code == 0, result.stdout
    assert "1 API call(s)" in result.stdout
    assert "cache hit" not in result.stdout


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


def test_check_diff_aware_mtime_drift_flags_source_without_doc(tmp_path: Path) -> None:
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
    assert "sources changed in this diff but the doc was not updated" in result.stdout


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
        assert finding["fix_command"] == "irminsul fix --check supersession"

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
