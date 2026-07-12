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
