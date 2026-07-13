"""Tests for binding readiness and the RFC-0034 report extensions."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.change.finalize import plan_finalize
from irminsul.change.readiness import (
    binding_readiness_to_json,
    build_binding_readiness_report,
    format_binding_readiness_plain,
)
from irminsul.change.report import (
    ChangeReport,
    build_change_report,
    change_report_to_json,
    format_change_status_plain,
    format_change_verify_plain,
)
from irminsul.cli import app
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

runner = CliRunner()

_BAD_FRONTMATTER = Path(__file__).parent / "fixtures" / "repos" / "bad-frontmatter"

_STALE_PIN = "@sha256:000000000000"


@pytest.fixture
def repo(fixture_repo: Callable[[str], Path]) -> Path:
    return fixture_repo("soft-change-binding")


@pytest.fixture
def binding_repo(fixture_repo: Callable[[str], Path]) -> Path:
    """A green repo whose accepted RFC 0001 (affects: [auth]) is mechanically
    ready; each test introduces exactly one defect."""
    return fixture_repo("soft-binding-readiness")


def _append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.write_text(f"{path.read_text(encoding='utf-8')}\n{text}\n", encoding="utf-8")


def _report(repo: Path, change: str) -> ChangeReport:
    return build_change_report(repo, load(find_config(repo)), change, env={})


def _scoped(report: ChangeReport) -> list[dict[str, object]]:
    payload = report.extra.get("scoped_findings", [])
    assert isinstance(payload, list)
    return payload


def _git_init(repo: Path) -> None:
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "T"),
        ("add", "."),
        ("commit", "-q", "-m", "init"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_readiness_clean_repo_is_ready(repo: Path) -> None:
    report = build_binding_readiness_report(repo, load(find_config(repo)))
    assert report.ready
    assert report.blockers == ()


def test_readiness_hard_errors_block() -> None:
    report = build_binding_readiness_report(_BAD_FRONTMATTER, load(find_config(_BAD_FRONTMATTER)))
    assert not report.ready
    assert report.blockers
    assert all(item.check for item in report.blockers)


def test_readiness_json_shape(repo: Path) -> None:
    report = build_binding_readiness_report(repo, load(find_config(repo)))
    data = json.loads(binding_readiness_to_json(report))
    assert data["version"] == 1
    assert data["ready"] is True
    assert isinstance(data["clues"], list)
    assert isinstance(data["repository_debt"], list)


def test_readiness_plain_output(repo: Path) -> None:
    report = build_binding_readiness_report(repo, load(find_config(repo)))
    assert "binding readiness: ready" in format_binding_readiness_plain(report)


def test_new_rfc_blocked_by_hard_errors(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["new", "rfc", "Blocked Idea", "--path", str(repo)])
    assert result.exit_code == 1
    assert "hard checks fail" in result.output
    assert not list((repo / "docs").glob("80-evolution/rfcs/*blocked-idea*"))


def test_new_rfc_force_overrides_block(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-frontmatter")
    result = runner.invoke(app, ["new", "rfc", "Forced Idea", "--force", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "created:" in result.output


def test_new_rfc_proceeds_when_ready(repo: Path) -> None:
    result = runner.invoke(app, ["new", "rfc", "Good Idea", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "created:" in result.output


def test_report_carries_repository_debt_key(repo: Path) -> None:
    _git_init(repo)
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    data = json.loads(change_report_to_json(report))
    assert "repository_debt" in data
    assert isinstance(data["repository_debt"], list)


def test_report_blocks_on_unresolved_required_update(repo: Path) -> None:
    _git_init(repo)
    rfc = repo / "docs" / "80-evolution" / "rfcs" / "0001-accepted-good.md"
    text = rfc.read_text(encoding="utf-8")
    rfc.write_text(
        text.replace(
            "required_updates: []",
            "required_updates:\n  - path: docs/30-workflows/missing.md\n    kind: update",
        ),
        encoding="utf-8",
    )
    report = build_change_report(repo, load(find_config(repo)), "0001-accepted-good", env={})
    assert any(b.code.startswith("decision-updates:") for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_binding_fixture_clean_tree_is_ready(binding_repo: Path) -> None:
    _git_init(binding_repo)
    report = _report(binding_repo, "0001-accepted-good")
    assert report.blockers == ()
    assert report.mechanically_ready_for == "implemented"
    assert _scoped(report) == []
    assert report.repository_debt == ()


def test_broken_anchor_in_affected_scope_blocks(binding_repo: Path) -> None:
    """An anchor pointing at a missing file is an error: it must block at least
    as hard as a stale one, and it must never vanish from the report."""
    _append(binding_repo, "docs/20-components/auth.md", "<!-- anchor: app/auth/gone.py#login -->")
    _git_init(binding_repo)

    report = _report(binding_repo, "0001-accepted-good")
    broken = [b for b in report.blockers if b.code == "broken-anchor"]
    assert len(broken) == 1
    assert "app/auth/gone.py" in broken[0].message
    assert broken[0].path == "docs/20-components/auth.md"
    assert report.mechanically_ready_for == "none"
    assert "app/auth/gone.py" in change_report_to_json(report)
    assert _scoped(report) == []  # promoted, so not double-reported


def test_missing_symbol_anchor_in_affected_scope_blocks(binding_repo: Path) -> None:
    _append(binding_repo, "docs/20-components/auth.md", "<!-- anchor: app/auth/login.py#logout -->")
    _git_init(binding_repo)

    report = _report(binding_repo, "0001-accepted-good")
    assert any(b.code == "broken-anchor" for b in report.blockers)
    assert report.mechanically_ready_for == "none"


def test_stale_anchor_outside_affects_stays_visible(binding_repo: Path) -> None:
    """billing is not in `affects`, so its stale anchor is not promoted to a
    blocker — but it is a changed path, so it must still be reported."""
    _git_init(binding_repo)
    _append(
        binding_repo,
        "docs/20-components/billing.md",
        f"<!-- anchor: app/billing/invoice.py#invoice {_STALE_PIN} -->",
    )

    report = _report(binding_repo, "0001-accepted-good")
    assert not any(b.code.endswith("anchor") for b in report.blockers)
    scoped = _scoped(report)
    assert [item["check"] for item in scoped] == ["claim-anchor"]
    assert scoped[0]["path"] == "docs/20-components/billing.md"


def test_decision_finding_outside_promoted_categories_stays_visible(binding_repo: Path) -> None:
    """A stale-claim finding mentions the RFC but is not one of the promoted
    categories; it must land in scoped findings rather than disappear."""
    _git_init(binding_repo)
    billing = binding_repo / "docs" / "20-components" / "billing.md"
    billing.write_text(
        billing.read_text(encoding="utf-8").replace(
            "tests:\n  - tests/test_binding_billing.py\n",
            "tests:\n  - tests/test_binding_billing.py\n"
            "claims:\n"
            "  - id: sso-live\n"
            "    state: planned\n"
            "    kind: feature\n"
            "    claim: SSO login is planned.\n"
            "    evidence:\n"
            "      - docs/80-evolution/rfcs/0001-accepted-good.md\n",
        ),
        encoding="utf-8",
    )

    report = _report(binding_repo, "0001-accepted-good")
    scoped = _scoped(report)
    assert [item["check"] for item in scoped] == ["decision-updates"]
    assert "sso-live" in str(scoped[0]["message"])
    assert not any(b.code.startswith("decision-updates:") for b in report.blockers)


def test_unowned_change_blocks_and_matches_finalize(binding_repo: Path) -> None:
    """`verify` must not report ready for a tree `finalize` will refuse."""
    _git_init(binding_repo)
    (binding_repo / "app" / "auth" / "sso.py").write_text(
        "def sso() -> None:\n    pass\n", encoding="utf-8"
    )
    (binding_repo / "app" / "utils").mkdir(parents=True)
    (binding_repo / "app" / "utils" / "helpers.py").write_text(
        "def helper() -> None:\n    pass\n", encoding="utf-8"
    )

    report = _report(binding_repo, "0001-accepted-good")
    assert [b.code for b in report.blockers] == ["unowned-change"]
    assert report.blockers[0].path == "app/utils/helpers.py"
    assert report.mechanically_ready_for == "none"

    config = load(find_config(binding_repo))
    plan = plan_finalize(
        build_graph(binding_repo, config),
        config,
        binding_repo,
        "0001-accepted-good",
        bindings={"sso-login": ["app/auth/sso.py#sso"]},
    )
    assert "unowned-change" in {b.code for b in plan.blockers}


def test_verify_plain_renders_scoped_findings(binding_repo: Path) -> None:
    _git_init(binding_repo)
    _append(
        binding_repo,
        "docs/20-components/auth.md",
        f"<!-- anchor: app/auth/login.py#login {_STALE_PIN} -->",
    )

    report = _report(binding_repo, "0002-draft-ready")
    out = format_change_verify_plain(report)
    assert "findings about this change: 1" in out
    assert "[claim-anchor] docs/20-components/auth.md:" in out
    assert "re-pin" in out


def test_status_plain_summarizes_scoped_findings(binding_repo: Path) -> None:
    _git_init(binding_repo)
    _append(
        binding_repo,
        "docs/20-components/auth.md",
        f"<!-- anchor: app/auth/login.py#login {_STALE_PIN} -->",
    )

    out = format_change_status_plain(_report(binding_repo, "0002-draft-ready"))
    assert "findings about this change: 1" in out


def test_repository_debt_counts_findings_not_warnings(binding_repo: Path) -> None:
    """billing.md is neither declared nor changed: its finding is debt, and the
    count is a finding count (soft checks emit errors too)."""
    _append(
        binding_repo,
        "docs/20-components/billing.md",
        f"<!-- anchor: app/billing/invoice.py#invoice {_STALE_PIN} -->",
    )
    _git_init(binding_repo)

    report = _report(binding_repo, "0001-accepted-good")
    assert report.repository_debt == (("claim-anchor", 1),)
    assert _scoped(report) == []
    data = json.loads(change_report_to_json(report))
    assert data["repository_debt"] == [{"check": "claim-anchor", "findings": 1}]


def test_lifecycle_queue_includes_accepted_backlog(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["list", "lifecycle", "--queue", "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    backlog = [item for item in data if item["kind"] == "implement"]
    assert {item["related_id"] for item in backlog} == {
        "0001-accepted-good",
        "0002-accepted-missing-affects",
    }
    assert all(item["suggested_command"].startswith("irminsul change status") for item in backlog)
