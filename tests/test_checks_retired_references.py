"""Tests for ADR-owned retired command and concept audits."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.retired_references import RetiredReferencesCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _write_config(repo: Path) -> None:
    (repo / "irminsul.toml").write_text(
        'project_name = "retirements"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )


def _write_doc(
    repo: Path,
    rel: str,
    *,
    doc_id: str,
    body: str,
    audience: str = "explanation",
    status: str = "stable",
    frontmatter_extra: list[str] | None = None,
) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"id: {doc_id}",
                f"title: {doc_id}",
                f"audience: {audience}",
                "tier: 2",
                f"status: {status}",
                "describes: []",
                *(frontmatter_extra or []),
                "---",
                "",
                f"# {doc_id}",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def _write_retirement_adr(
    repo: Path,
    *,
    rel: str = "docs/50-decisions/0001-retire-render.md",
    doc_id: str = "0001-retire-render",
    status: str = "stable",
    command: str = "irminsul render",
    concept: str = "reference layer",
) -> None:
    _write_doc(
        repo,
        rel,
        doc_id=doc_id,
        audience="adr",
        status=status,
        body=f"Retire `{command}` and the {concept}.",
        frontmatter_extra=[
            "retires:",
            "  - id: render-command",
            "    kind: cli-command",
            "    surface_identity: render",
            "    matches:",
            f"      - {command}",
            "    guidance: Use `irminsul surface` instead.",
            "  - id: reference-layer",
            "    kind: concept",
            "    matches:",
            f"      - {concept}",
            "    guidance: Keep reference facts with their owning component.",
        ],
    )


def _findings(repo: Path):
    graph = build_graph(repo, load(repo / "irminsul.toml"))
    return RetiredReferencesCheck().run(graph)


def test_flags_retired_command_in_fenced_example_with_provenance(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/cli.md",
        doc_id="cli",
        body="```console\nirminsul   render --output site\n```",
    )

    findings = _findings(tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == "retired-reference"
    assert finding.path == Path("docs/20-components/cli.md")
    assert finding.line == 13
    assert finding.data == {
        "problem": "retired-reference",
        "kind": "cli-command",
        "match": "irminsul render",
        "retirement-id": "render-command",
        "declared-by": "docs/50-decisions/0001-retire-render.md",
        "guidance": "Use `irminsul surface` instead.",
        "occurrences": "1",
    }


def test_concept_matching_is_case_insensitive_and_token_bounded(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body="The REFERENCE LAYER remains. A reference layered view is unrelated.",
    )

    findings = _findings(tmp_path)

    assert [finding.data["match"] for finding in findings if finding.data] == ["reference layer"]


def test_command_matching_is_case_sensitive_and_token_bounded(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body="`Irminsul render` and `irminsul renderer` are different identities.",
    )

    assert _findings(tmp_path) == []


def test_skips_historical_and_nonstable_atoms(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/80-evolution/rfcs/0002-old.md",
        doc_id="0002-old",
        body="Run irminsul render.",
    )
    _write_doc(
        tmp_path,
        "docs/20-components/draft.md",
        doc_id="draft",
        status="draft",
        body="Run irminsul render.",
    )
    _write_doc(
        tmp_path,
        "docs/20-components/removed.md",
        doc_id="removed",
        status="removed",
        body="Run irminsul render.",
    )

    assert _findings(tmp_path) == []


def test_exact_inline_link_to_owner_is_historical_citation(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body=(
            "The former [`irminsul render`](../50-decisions/0001-retire-render.md) "
            "command was removed."
        ),
    )

    assert _findings(tmp_path) == []


def test_exact_reference_link_to_owner_is_historical_citation(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body=(
            "The former [`irminsul render`][retirement] command was removed.\n\n"
            "[retirement]: ../50-decisions/0001-retire-render.md"
        ),
    )

    assert _findings(tmp_path) == []


def test_nearby_owner_link_does_not_hide_unlinked_phrase(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body=(
            "The [retirement decision](../50-decisions/0001-retire-render.md) "
            "removed `irminsul render`."
        ),
    )

    assert len(_findings(tmp_path)) == 1


def test_exact_owner_citation_does_not_hide_second_unlinked_occurrence(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body=(
            "[`irminsul render`](../50-decisions/0001-retire-render.md) is historical; "
            "do not run irminsul render today."
        ),
    )

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].data is not None
    assert findings[0].data["occurrences"] == "1"


def test_masks_destinations_urls_definitions_and_comments(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body=(
            "[safe](https://example.test/irminsul%20render)\n"
            "https://example.test/reference%20layer\n"
            "[old]: ../irminsul-render/reference-layer\n"
            "<!-- irminsul render and reference layer -->"
        ),
    )

    assert _findings(tmp_path) == []


def test_scans_current_top_level_guidance(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "README.md").write_text("Use irminsul render.\n", encoding="utf-8")

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].path == Path("README.md")
    assert findings[0].doc_id is None
    assert findings[0].line == 1


def test_aggregates_repeated_mentions_per_retirement_and_doc(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body="Run irminsul render.\n\nThen run irminsul render again.",
    )

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].data is not None
    assert findings[0].data["occurrences"] == "2"


def test_live_cli_identity_disables_retirement_tombstone(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "import typer\n\napp = typer.Typer()\n\n@app.command()\ndef render():\n    pass\n",
        encoding="utf-8",
    )
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body="Run irminsul render.",
    )

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].category == "retirement-still-live"
    assert findings[0].path == Path("docs/50-decisions/0001-retire-render.md")
    assert findings[0].data == {
        "problem": "retirement-still-live",
        "kind": "cli-command",
        "retirement-id": "render-command",
        "surface-identity": "render",
    }


def test_reports_inactive_retirement_owner(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path, status="draft")

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].category == "inactive-retirement"
    assert findings[0].data == {
        "problem": "inactive-retirement",
        "reason": "owner-not-stable-adr",
    }


def test_reports_duplicate_retirement_provenance_deterministically(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_retirement_adr(
        tmp_path,
        rel="docs/50-decisions/0002-retire-render-again.md",
        doc_id="0002-retire-render-again",
    )

    findings = _findings(tmp_path)

    ambiguous = [finding for finding in findings if finding.category == "ambiguous-retirement"]
    assert len(ambiguous) == 2
    assert all(
        finding.data is not None
        and finding.data["declared-by"] == "docs/50-decisions/0001-retire-render.md"
        for finding in ambiguous
    )
