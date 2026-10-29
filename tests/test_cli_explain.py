"""Tests for `irminsul explain`."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from irminsul.checks import REGISTRY
from irminsul.cli import app

runner = CliRunner()


def test_explain_known_code_prints_summary_and_explanation() -> None:
    result = runner.invoke(app, ["explain", "links/broken-link"])
    assert result.exit_code == 0, result.output
    assert "links/broken-link" in result.output
    assert "check: links" in result.output
    assert "does not resolve to an existing file" in result.output
    assert "stays inside its own repository" in result.output
    assert "full URL" in result.output and "code span" in result.output


def test_explain_unknown_code_exits_two_without_dumping_the_registry() -> None:
    result = runner.invoke(app, ["explain", "not-a-check/not-a-code"])
    assert result.exit_code == 2
    assert "unknown code 'not-a-check/not-a-code'" in result.output
    assert "[frontmatter]" not in result.output
    assert "frontmatter/missing-frontmatter" not in result.output
    assert "`irminsul explain` with no argument lists every code" in result.output


def test_explain_unknown_name_offers_the_nearest_check_and_code_names() -> None:
    near_check = runner.invoke(app, ["explain", "prose-file-referenc"])
    assert near_check.exit_code == 2
    assert "did you mean 'prose-file-reference'" in near_check.output

    near_code = runner.invoke(app, ["explain", "links/broken-lnk"])
    assert near_code.exit_code == 2
    assert "'links/broken-link'" in near_code.output


def test_explain_check_name_lists_only_that_checks_codes_with_class_and_summary() -> None:
    result = runner.invoke(app, ["explain", "prose-file-reference"])
    assert result.exit_code == 0, result.output
    assert "check: prose-file-reference" in result.output
    assert "prose-file-reference/unlinked-reference (certain)" in result.output
    assert "A local `.md` filename is named in plain text without a Markdown link." in result.output
    assert "Convert it to a link" not in result.output
    assert "links/broken-link" not in result.output
    assert "[frontmatter]" not in result.output


@pytest.mark.parametrize(
    "code",
    [
        "prose-file-reference/ignore-end-without-start",
        "prose-file-reference/ignore-start-without-end",
        "prose-file-reference/stale-suppression",
    ],
)
def test_the_prose_file_reference_marker_codes_are_unknown(code: str) -> None:
    result = runner.invoke(app, ["explain", code])

    assert result.exit_code == 2 and f"unknown code '{code}'" in result.output


def test_explain_describes_the_unknown_path_hint() -> None:
    result = runner.invoke(app, ["explain", "code-references/unknown-path"])

    assert result.exit_code == 0, result.output
    assert "class: hint" in result.output
    assert "ignore comment" in result.output


def test_explain_says_how_to_answer_an_unverifiable_adoption_source() -> None:
    result = runner.invoke(app, ["explain", "adoption-record/source-unverifiable"])

    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    assert "paths.sources" in flat
    assert "fetch-depth: 0" in flat
    assert "diff-integrity/adoption-source-rebound" in flat


_PASS_SUMMARIES = {
    "adoption-record": (
        "The adoption record must load and its entries must be verifiable, or it excepts nothing."
    ),
    "history-depth": "The checkout must hold enough git history for the checks that read it.",
    "co-change": "Docs must ship in the same change as the code they claim.",
    "diff-integrity": "A change must not quietly lower the gates it is judged by.",
    "new-dependency": "An import edge the diff introduced that the importing doc does not declare.",
    "ignore-comment": (
        "Ignore comments must name a known hint or time finding, give a reason, and "
        "suppress something."
    ),
}


def test_a_pass_is_summarised_by_what_it_judges() -> None:
    """The summary is the first line of the class docstring, which for a pass once said
    that the class gave the pass a `name` and `explanations`: a maintainer's note, shown to a
    user who asked what the pass is."""
    from irminsul.checks.pipeline import finding_sources

    for name, summary in _PASS_SUMMARIES.items():
        first_code = sorted(finding_sources()[name].explanations)[0]
        for target in (name, first_code):
            result = runner.invoke(app, ["explain", target])
            assert result.exit_code == 0, (target, result.output)
            assert f"check: {name} — {summary}" in result.output, (target, result.output)


def test_explain_resolves_every_explainable_check_by_name() -> None:
    from irminsul.checks.pipeline import finding_sources

    for check_name, cls in finding_sources().items():
        result = runner.invoke(app, ["explain", check_name])
        assert result.exit_code == 0, (check_name, result.output)
        for code in cls.explanations:
            assert code in result.output, (check_name, code)


def test_explain_no_args_lists_all_codes_grouped_by_check() -> None:
    result = runner.invoke(app, ["explain"])
    assert result.exit_code == 0, result.output
    for check_name in ("frontmatter", "links", "supersession"):
        assert f"[{check_name}]" in result.output


def test_explain_listing_covers_every_registered_check_code() -> None:
    result = runner.invoke(app, ["explain"])
    assert result.exit_code == 0, result.output
    for check_name, cls in REGISTRY.items():
        assert f"[{check_name}]" in result.output
        for code in cls.explanations:
            assert code in result.output


def test_explain_resolves_unregistered_co_change_code() -> None:
    """co-change is in neither registry (it only runs under `--diff`), but the
    CLI prints its code, so `explain` must resolve it like any other."""
    result = runner.invoke(app, ["explain", "co-change/unreflected-change"])
    assert result.exit_code == 0, result.output
    assert "check: co-change" in result.output
    assert "changed in the diff" in result.output


def test_explain_no_args_listing_includes_co_change() -> None:
    result = runner.invoke(app, ["explain"])
    assert result.exit_code == 0, result.output
    assert "[co-change]" in result.output
    assert "co-change/unreflected-change" in result.output


def test_explain_summaries_differ_between_checks() -> None:
    """Each check must explain itself with its own summary line, not a generic one."""

    def summary_line(code: str) -> str:
        result = runner.invoke(app, ["explain", code])
        assert result.exit_code == 0, result.output
        (line,) = [ln for ln in result.output.splitlines() if ln.startswith("check: ")]
        return line

    prose = summary_line("prose-file-reference/unlinked-reference")
    claims = summary_line("claim-provenance/evidence-drift")
    assert prose.removeprefix("check: prose-file-reference") != claims.removeprefix(
        "check: claim-provenance"
    )
    assert "—" in prose and "—" in claims  # both carry a real summary, not just a name


def test_explain_reports_the_finding_class() -> None:
    """The class decides whether a finding blocks, and was readable only from source.

    An ADR carried a hand-written table of every code's class instead; it drifted,
    listing a code under its old class after the code was promoted.
    """
    result = runner.invoke(app, ["explain", "uniqueness/undocumented-file"])
    assert result.exit_code == 0, result.output
    assert "class: certain" in result.output

    hint = runner.invoke(app, ["explain", "claim-anchor/pinned-drift"])
    assert hint.exit_code == 0, hint.output
    assert "class: hint" in hint.output


def test_every_explainable_code_declares_a_class() -> None:
    """A code the pipeline cannot classify is one `explain` describes without saying
    whether it blocks."""
    from irminsul.checks.pipeline import class_of, finding_sources

    unclassified = [
        code
        for cls in finding_sources().values()
        for code in (getattr(cls, "explanations", {}) or {})
        if class_of(code) is None
    ]
    assert unclassified == []
