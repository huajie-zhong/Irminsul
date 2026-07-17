"""Tests for `irminsul explain`."""

from __future__ import annotations

from typer.testing import CliRunner

from irminsul.checks import HARD_REGISTRY, SOFT_REGISTRY
from irminsul.cli import app

runner = CliRunner()


def test_explain_known_code_prints_summary_and_explanation() -> None:
    result = runner.invoke(app, ["explain", "links/broken-link"])
    assert result.exit_code == 0, result.output
    assert "links/broken-link" in result.output
    assert "check: links" in result.output
    assert "does not resolve to an existing file" in result.output


def test_explain_unknown_code_lists_all_and_exits_one() -> None:
    result = runner.invoke(app, ["explain", "not-a-check/not-a-code"])
    assert result.exit_code == 1
    assert "unknown code" in result.output
    assert "[frontmatter]" in result.output
    assert "frontmatter/missing-frontmatter" in result.output


def test_explain_no_args_lists_all_codes_grouped_by_check() -> None:
    result = runner.invoke(app, ["explain"])
    assert result.exit_code == 0, result.output
    for check_name in ("frontmatter", "links", "supersession"):
        assert f"[{check_name}]" in result.output


def test_explain_listing_covers_every_registered_check_code() -> None:
    result = runner.invoke(app, ["explain"])
    assert result.exit_code == 0, result.output
    for check_name, cls in {**HARD_REGISTRY, **SOFT_REGISTRY}.items():
        assert f"[{check_name}]" in result.output
        for code in cls.explanations:
            assert code in result.output
