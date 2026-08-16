"""Tests for ADR-owned retired command and concept audits."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.retired_references import RetiredReferencesCheck, _guidance_sources
from irminsul.config import load
from irminsul.docgraph import build_graph


def _write_config(repo: Path) -> None:
    (repo / "irminsul.toml").write_text(
        'project_name = "retirements"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )


def test_guidance_sources_normalize_absolute_docs_root_paths(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "GLOSSARY.md").write_text("Glossary.\n", encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "retirements"',
                "[paths]",
                f'docs_root = "{docs_root.as_posix()}"',
                'source_roots = ["src"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    graph = build_graph(tmp_path, load(tmp_path / "irminsul.toml"))

    glossary = next(
        source for source in _guidance_sources(graph) if source.path.name == "GLOSSARY.md"
    )
    assert glossary.path == Path("docs/GLOSSARY.md")


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


def test_capitalised_concept_does_not_match_lowercase_prose(tmp_path: Path) -> None:
    """`Topology A` folded to lower case matched "whatever topology a project
    picks" — a whole-token match on ordinary English, so word boundaries could
    not save it. A capital in the declaration marks a proper name and keeps the
    match case-sensitive."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path, concept="Topology A")
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body="Whatever topology a project picks, the checks behave the same.",
    )

    assert _findings(tmp_path) == []


def test_capitalised_concept_still_matches_its_declared_spelling(tmp_path: Path) -> None:
    """The other half: case sensitivity must not cost the tombstone its job."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path, concept="Topology A")
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body="Scaffold a private docs tree with Topology A.",
    )

    findings = _findings(tmp_path)

    assert [finding.data["match"] for finding in findings if finding.data] == ["Topology A"]


def test_both_spellings_of_one_concept_are_distinct_declarations(tmp_path: Path) -> None:
    """A tombstone that wants a capitalised name matched loosely lists both
    spellings. They compile to different patterns, so neither is reported as an
    ambiguous duplicate of the other, and a line that matches both is still one
    finding because both belong to the same entry."""
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/50-decisions/0001-retire-lettered.md",
        doc_id="0001-retire-lettered",
        audience="adr",
        body="The lettered names are gone.",
        frontmatter_extra=[
            "retires:",
            "  - id: lettered-topologies",
            "    kind: concept",
            "    matches:",
            "      - Topology A",
            "      - topology a",
            "    guidance: Name the layout instead.",
        ],
    )
    _write_doc(
        tmp_path,
        "docs/20-components/current.md",
        doc_id="current",
        body="Topology A is what we call it.",
    )

    findings = _findings(tmp_path)

    assert [finding.category for finding in findings] == ["retired-reference"]
    assert findings[0].path == Path("docs/20-components/current.md")


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


def test_audits_other_adrs(tmp_path: Path) -> None:
    """ADRs are current decisions, not historical record. The audit used to skip
    every doc with `audience: adr`, which is how a shipped ADR kept instructing
    readers to run a command that no longer exists."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/50-decisions/0002-other.md",
        doc_id="0002-other",
        audience="adr",
        body="Build the site with irminsul render.",
    )

    findings = _findings(tmp_path)

    assert [f.path for f in findings] == [Path("docs/50-decisions/0002-other.md")]


def test_owner_adr_is_never_audited_against_its_own_tombstones(tmp_path: Path) -> None:
    """The counterweight: an ADR must be able to name what it retired, in its
    frontmatter `matches:` list and in the prose explaining the decision."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)

    assert _findings(tmp_path) == []


def test_audits_the_agent_manifests(tmp_path: Path) -> None:
    """`irminsul init` tells every user to point their agent at these files, and
    none of them is a graph node — the AGENTS.md files are exempt top-level
    names and CLAUDE.md sits outside docs_root."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "AGENTS.md").write_text("Use irminsul render.\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Use irminsul render.\n", encoding="utf-8")
    (tmp_path / "docs" / "AGENTS.md").write_text("Use irminsul render.\n", encoding="utf-8")

    assert {f.path for f in _findings(tmp_path)} == {
        Path("AGENTS.md"),
        Path("CLAUDE.md"),
        Path("docs/AGENTS.md"),
    }


def test_audits_frontmatter(tmp_path: Path) -> None:
    """A retired name misleads just as much in a `title:` or `summary:` as in
    prose, and both are read by agents browsing the manifest."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/thing.md",
        doc_id="thing",
        body="Nothing to see.",
        frontmatter_extra=["summary: Wraps the reference layer."],
    )

    findings = _findings(tmp_path)

    assert [f.path for f in findings] == [Path("docs/20-components/thing.md")]
    assert findings[0].line == 8


def test_skips_the_generated_manifest_region(tmp_path: Path) -> None:
    """`regen agents-md` builds those rows from the titles of the docs it
    indexes, including RFCs whose titles ADR-0016 freezes. A finding there names
    a line nobody may edit and that `regen` would rewrite identically. Lines
    outside the markers are still audited, at their true line numbers."""
    from irminsul.regen.agents_md import GENERATED_END, GENERATED_START

    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "docs" / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Agents",
                GENERATED_START,
                "| doc | Uses the reference layer |",
                GENERATED_END,
                "Hand-written: the reference layer is how we do it.",
            ]
        ),
        encoding="utf-8",
    )

    findings = _findings(tmp_path)

    assert [f.line for f in findings] == [5]


def test_unmatched_generated_marker_is_reported_and_suppresses_nothing(tmp_path: Path) -> None:
    """A start marker with no end used to open the generated region and never
    close it, so one stray line switched this hard check off for the rest of the
    file — silently, since nothing reported the marker. Only balanced markers
    blank anything now, and the unmatched one is itself an error."""
    from irminsul.regen.agents_md import GENERATED_START

    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "README.md").write_text(
        f"# Demo\n{GENERATED_START}\nRun irminsul render.\n", encoding="utf-8"
    )

    findings = _findings(tmp_path)

    assert [(f.category, f.line) for f in findings] == [
        ("unmatched-generated-marker", 2),
        ("retired-reference", 3),
    ]
    assert all(f.severity.value == "error" for f in findings)


def test_retired_reference_findings_are_errors(tmp_path: Path) -> None:
    """ADR-0022 nominates this audit as the thing that makes stale guidance
    fail. CI's dogfood step runs no `--strict`, so a warning would report and
    never block."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "README.md").write_text("Use irminsul render.\n", encoding="utf-8")

    findings = _findings(tmp_path)

    assert [f.severity.value for f in findings] == ["error"]


def test_retired_references_is_a_hard_check() -> None:
    """Hard checks block regardless of `--strict`, which is what makes
    ADR-0022's safety-net claim true rather than aspirational."""
    from irminsul.checks import HARD_REGISTRY, SOFT_REGISTRY

    assert RetiredReferencesCheck.name in HARD_REGISTRY
    assert RetiredReferencesCheck.name not in SOFT_REGISTRY
