"""Tests for ADR-owned retired command and concept audits."""

from __future__ import annotations

from pathlib import Path

import pytest

from irminsul.checks.retired_references import RetiredReferencesCheck, _guidance_sources

from .conftest import load_graph, run_check, write_config, write_doc


def _write_config(repo: Path) -> None:
    write_config(repo, project_name="retirements", source_roots=["src"])


def test_a_guidance_file_that_does_not_decode_has_no_lines(tmp_path: Path) -> None:
    """This reader runs before the other three guidance readers and was the only one that
    did not guard its read. A `README.md` an editor saved as UTF-16 therefore ended
    `irminsul check` in a traceback — including the run that would have printed
    `agents-manifest/manifest-unreadable`, whose explanation says how to repair it.

    Not decoding is now *reported* as well as survived. Guarding the read stopped the
    traceback but left the file audited by nothing — every reader skips it — so a run could
    exit clean having checked none of its links, references or ignore comments."""
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "GLOSSARY.md").write_text("Glossary.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n\nProse.\n", encoding="utf-16")
    _write_config(tmp_path)

    graph = load_graph(tmp_path)
    sources = _guidance_sources(graph)

    readme = next(source for source in sources if source.path.name == "README.md")
    assert readme.lines == ()
    assert readme.unreadable is not None
    # The rest of the tree is still read, and the check still runs to completion.
    assert any(source.path.name == "GLOSSARY.md" for source in sources)
    findings = RetiredReferencesCheck().run(graph)
    assert [finding.code for finding in findings] == ["retired-references/guidance-unreadable"]
    assert findings[0].path.name == "README.md"


def test_guidance_sources_normalize_rooted_docs_root_paths(tmp_path: Path) -> None:
    """A leading slash means the repository root, and normalizes away.

    An absolute `docs_root` is rejected by the config schema: it is not portable across
    machines, and one reaching outside the repository used to be walked.
    """
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "GLOSSARY.md").write_text("Glossary.\n", encoding="utf-8")
    (tmp_path / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "retirements"',
                "[paths]",
                'docs_root = "/docs/"',
                'source_roots = ["src"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    graph = load_graph(tmp_path)

    glossary = next(
        source for source in _guidance_sources(graph) if source.path.name == "GLOSSARY.md"
    )
    assert glossary.path == Path("docs/GLOSSARY.md")


def _write_retirement_adr(
    repo: Path,
    *,
    rel: str = "docs/decisions/0001-retire-render.md",
    doc_id: str = "0001-retire-render",
    status: str = "stable",
    command: str = "irminsul render",
    concept: str = "reference layer",
) -> None:
    write_doc(
        repo,
        rel,
        doc_id=doc_id,
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
    return run_check(RetiredReferencesCheck, repo)


def test_flags_retired_command_in_fenced_example_with_provenance(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/cli.md",
        doc_id="cli",
        body="```console\nirminsul   render --output site\n```",
    )

    findings = _findings(tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "retired-references/retired-reference"
    assert finding.path == Path("docs/components/cli.md")
    assert finding.line == 11
    assert finding.data == {
        "kind": "cli-command",
        "match": "irminsul render",
        "retirement-id": "render-command",
        "declared-by": "docs/decisions/0001-retire-render.md",
        "guidance": "Use `irminsul surface` instead.",
        "occurrences": "1",
    }


def test_concept_matching_is_case_insensitive_and_token_bounded(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/current.md",
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
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="Whatever topology a project picks, the checks behave the same.",
    )

    assert _findings(tmp_path) == []


def test_capitalised_concept_still_matches_its_declared_spelling(tmp_path: Path) -> None:
    """The other half: case sensitivity must not cost the tombstone its job."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path, concept="Topology A")
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="Scaffold a private docs tree with Topology A.",
    )

    findings = _findings(tmp_path)

    assert [finding.data["match"] for finding in findings if finding.data] == ["Topology A"]


def test_both_spellings_of_one_concept_are_distinct_declarations(tmp_path: Path) -> None:
    """A tombstone that wants a capitalised name matched loosely lists both
    spellings. They fold to one dedup key but belong to one entry, so neither
    is reported as an ambiguous duplicate of the other, both patterns stay
    active with their own case semantics, and a line that matches both is
    still one finding because both belong to the same entry."""
    _write_config(tmp_path)
    write_doc(
        tmp_path,
        "docs/decisions/0001-retire-lettered.md",
        doc_id="0001-retire-lettered",
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
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="Topology A is what we call it.",
    )

    findings = _findings(tmp_path)

    assert [finding.code for finding in findings] == ["retired-references/retired-reference"]
    assert findings[0].path == Path("docs/components/current.md")


def test_case_variant_tombstones_across_adrs_warn_and_dedupe(tmp_path: Path) -> None:
    """Two ADRs retiring one concept in different case name the same thing —
    the dedup key folds case for every concept phrase, capitalised or not.
    Keying them apart kept both rules active: no ambiguous-retirement warning,
    and one guidance line drew two hard errors for one reference. The earlier
    ADR's declaration is canonical and its smart-case matching semantics
    survive untouched."""
    _write_config(tmp_path)
    for doc_id, rel, retirement_id, phrase in (
        ("0001-retire-a", "docs/decisions/0001-retire-a.md", "docs-only", "docs-only topology"),
        (
            "0002-retire-b",
            "docs/decisions/0002-retire-b.md",
            "docs-only-2",
            "Docs-Only Topology",
        ),
    ):
        write_doc(
            tmp_path,
            rel,
            doc_id=doc_id,
            body="Gone.",
            frontmatter_extra=[
                "retires:",
                f"  - id: {retirement_id}",
                "    kind: concept",
                "    matches:",
                f"      - {phrase}",
                "    guidance: Use the siblings layout.",
            ],
        )
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="The Docs-Only Topology still works.",
    )

    findings = _findings(tmp_path)

    ambiguous = [f for f in findings if f.code == "retired-references/ambiguous-retirement"]
    assert [f.path for f in ambiguous] == [Path("docs/decisions/0002-retire-b.md")]
    on_guidance = [
        f
        for f in findings
        if f.code == "retired-references/retired-reference"
        and f.path == Path("docs/components/current.md")
    ]
    assert len(on_guidance) == 1
    assert on_guidance[0].data is not None
    assert on_guidance[0].data["declared-by"] == "docs/decisions/0001-retire-a.md"


def test_command_matching_is_case_sensitive_and_token_bounded(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="`Irminsul render` and `irminsul renderer` are different identities.",
    )

    assert _findings(tmp_path) == []


def test_skips_historical_and_retired_atoms(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/rfcs/0002-old.md",
        doc_id="0002-old",
        body="Run irminsul render.",
    )
    write_doc(
        tmp_path,
        "docs/components/deprecated.md",
        doc_id="deprecated",
        status="deprecated",
        body="Run irminsul render.",
    )
    write_doc(
        tmp_path,
        "docs/components/removed.md",
        doc_id="removed",
        status="removed",
        body="Run irminsul render.",
    )

    assert _findings(tmp_path) == []


def test_a_draft_is_audited_like_a_stable_doc(tmp_path: Path) -> None:
    """A retired command is as wrong in a draft as in a stable doc, so `status: draft` is
    not a place to keep one."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/draft.md",
        doc_id="draft",
        status="draft",
        body="Run irminsul render.",
    )

    findings = _findings(tmp_path)

    assert [(f.code, f.path.as_posix()) for f in findings] == [
        ("retired-references/retired-reference", "docs/components/draft.md")
    ]


def test_exact_inline_link_to_owner_is_historical_citation(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body=(
            "The former [`irminsul render`](../decisions/0001-retire-render.md) "
            "command was removed."
        ),
    )

    assert _findings(tmp_path) == []


def test_exact_reference_link_to_owner_is_historical_citation(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body=(
            "The former [`irminsul render`][retirement] command was removed.\n\n"
            "[retirement]: ../decisions/0001-retire-render.md"
        ),
    )

    assert _findings(tmp_path) == []


def test_nearby_owner_link_does_not_hide_unlinked_phrase(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body=(
            "The [retirement decision](../decisions/0001-retire-render.md) "
            "removed `irminsul render`."
        ),
    )

    assert len(_findings(tmp_path)) == 1


def test_exact_owner_citation_does_not_hide_second_unlinked_occurrence(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body=(
            "[`irminsul render`](../decisions/0001-retire-render.md) is historical; "
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
    write_doc(
        tmp_path,
        "docs/components/current.md",
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
    write_doc(
        tmp_path,
        "docs/components/current.md",
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
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="Run irminsul render.",
    )

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "retired-references/retirement-still-live"
    assert findings[0].path == Path("docs/decisions/0001-retire-render.md")
    assert findings[0].data == {
        "kind": "cli-command",
        "retirement-id": "render-command",
        "surface-identity": "render",
    }


def test_reports_inactive_retirement_owner(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path, status="draft")

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "retired-references/inactive-retirement"
    assert findings[0].data == {
        "reason": "owner-not-stable-adr",
    }


def test_reports_duplicate_retirement_provenance_deterministically(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    _write_retirement_adr(
        tmp_path,
        rel="docs/decisions/0002-retire-render-again.md",
        doc_id="0002-retire-render-again",
    )

    findings = _findings(tmp_path)

    ambiguous = [
        finding for finding in findings if finding.code == "retired-references/ambiguous-retirement"
    ]
    assert len(ambiguous) == 2
    assert all(
        finding.data is not None
        and finding.data["declared-by"] == "docs/decisions/0001-retire-render.md"
        for finding in ambiguous
    )


def test_audits_other_adrs(tmp_path: Path) -> None:
    """ADRs are current decisions, not historical record, so they are audited:
    an ADR must not instruct readers to run a retired command."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/decisions/0002-other.md",
        doc_id="0002-other",
        body="Build the site with irminsul render.",
    )

    findings = _findings(tmp_path)

    assert [f.path for f in findings] == [Path("docs/decisions/0002-other.md")]


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
    write_doc(
        tmp_path,
        "docs/components/thing.md",
        doc_id="thing",
        body="Nothing to see.",
        frontmatter_extra=["summary: Wraps the reference layer."],
    )

    findings = _findings(tmp_path)

    assert [f.path for f in findings] == [Path("docs/components/thing.md")]
    assert findings[0].line == 6


def test_another_records_tombstones_are_data_not_prose(tmp_path: Path) -> None:
    """A second record's `retires:` block names what *it* retired, and its `matches:` and
    `guidance:` text can contain a phrase the first record retired. That block is data, not
    a sentence presenting the phrase as live, so only its title and summary are audited."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    write_doc(
        tmp_path,
        "docs/decisions/0002-retire-cache.md",
        doc_id="0002-retire-cache",
        body="The cache is gone too.",
        frontmatter_extra=[
            "retires:",
            "  - id: reference-layer-cache",
            "    kind: concept",
            "    matches:",
            "      - reference layer cache",
            "    guidance: Drop the reference layer cache with it.",
        ],
    )

    assert _findings(tmp_path) == []


def test_skips_the_generated_manifest_region(tmp_path: Path) -> None:
    """`regen agents-md` builds those rows from the titles of the docs it
    indexes, including sealed RFCs whose titles cannot change. A finding there names
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
    """A start marker with no end must not open a generated region that switches
    this hard check off for the rest of the file. Only balanced markers blank
    anything, and the unmatched one is itself an error."""
    from irminsul.regen.agents_md import GENERATED_START

    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "docs" / "AGENTS.md").write_text(
        f"# Agents\n{GENERATED_START}\nRun irminsul render.\n", encoding="utf-8"
    )

    findings = _findings(tmp_path)

    assert [(f.code, f.line) for f in findings] == [
        ("retired-references/unmatched-generated-marker", 2),
        ("retired-references/retired-reference", 3),
    ]
    assert all(f.severity.value == "error" for f in findings)


def test_marker_text_outside_the_manifest_is_ordinary_prose(tmp_path: Path) -> None:
    """Only the manifest carries a generated region, so only the manifest is
    read for markers. Anywhere else the marker text is an example: a balanced
    pair does not blank the stale guidance between it, and a lone start marker
    is not an unmatched region. Otherwise a fenced example that quoted the
    markers either failed the build or switched a hard check off."""
    from irminsul.regen.agents_md import GENERATED_END, GENERATED_START

    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "README.md").write_text(
        "\n".join(
            [
                "# Demo",
                "```markdown",
                GENERATED_START,
                "Run irminsul render.",
                GENERATED_END,
                "```",
                "The region opens with:",
                "```",
                GENERATED_START,
                "```",
            ]
        ),
        encoding="utf-8",
    )

    findings = _findings(tmp_path)

    assert [(f.code, f.line) for f in findings] == [("retired-references/retired-reference", 4)]


def test_manifest_fenced_marker_example_opens_no_region(tmp_path: Path) -> None:
    """The manifest's curated prose may quote the marker in a fenced example.
    Reading that as the region start paired it with the real end and blanked
    the curated prose between — stale guidance included — so fenced lines are
    skipped and only the real region is blanked."""
    from irminsul.regen.agents_md import GENERATED_END, GENERATED_START

    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "docs" / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Agents",
                "```",
                GENERATED_START,
                "```",
                "Hand-written: the reference layer is how we do it.",
                GENERATED_START,
                "| doc | Uses the reference layer |",
                GENERATED_END,
            ]
        ),
        encoding="utf-8",
    )

    findings = _findings(tmp_path)

    assert [(f.code, f.line) for f in findings] == [("retired-references/retired-reference", 5)]


def test_manifest_markers_on_one_line_close_the_region(tmp_path: Path) -> None:
    """A start and end on one line never paired — the end was only looked for
    on later lines — so the manifest reported an unmatched marker whose
    suggested fix was already on that line."""
    from irminsul.regen.agents_md import GENERATED_END, GENERATED_START

    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "docs" / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Agents",
                f"{GENERATED_START} Uses the reference layer {GENERATED_END}",
                "Hand-written: the reference layer is how we do it.",
            ]
        ),
        encoding="utf-8",
    )

    findings = _findings(tmp_path)

    assert [(f.code, f.line) for f in findings] == [("retired-references/retired-reference", 3)]


def test_manifest_with_two_generated_pairs_blanks_neither(tmp_path: Path) -> None:
    """Which pair is the generated table is not for this check to guess, and a guess that
    blanked both would switch a hard check off for every row between and inside them."""
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
                GENERATED_START,
                "| doc | Uses the reference layer again |",
                GENERATED_END,
            ]
        ),
        encoding="utf-8",
    )

    findings = _findings(tmp_path)

    assert [(f.code, f.line, f.data["occurrences"]) for f in findings] == [
        ("retired-references/retired-reference", 3, "2")
    ]


def test_retired_reference_findings_are_errors(tmp_path: Path) -> None:
    """CI's dogfood step does not fail on hints, so a warning would report and never
    block."""
    _write_config(tmp_path)
    _write_retirement_adr(tmp_path)
    (tmp_path / "README.md").write_text("Use irminsul render.\n", encoding="utf-8")

    findings = _findings(tmp_path)

    assert [f.severity.value for f in findings] == ["error"]


def test_a_retired_reference_is_certain() -> None:
    """Certain findings block regardless of `--fail-on`, which is what makes
    retirement enforceable rather than advisory."""
    from irminsul.checks import REGISTRY, FindingClass

    assert RetiredReferencesCheck.name in REGISTRY
    assert (
        RetiredReferencesCheck.classes["retired-references/retired-reference"]
        is FindingClass.certain
    )


def test_unreadable_guidance_cannot_be_baselined() -> None:
    """A guidance file that cannot be read is one every check silently skips — links, code
    references, retired references, ignore comments. Baselining the single finding that says
    so would turn a fail-closed diagnostic back into a green run, which is exactly what the
    suppression-audit set refuses."""
    from irminsul.checks.pipeline import audits_suppression

    assert "retired-references/guidance-unreadable" in audits_suppression()


def _write_concept_adr(repo: Path, doc_id: str, concepts: dict[str, list[str]]) -> None:
    extra = ["retires:"]
    for entry_id, matches in concepts.items():
        extra += [f"  - id: {entry_id}", "    kind: concept", "    matches:"]
        extra += [f'      - "{match}"' for match in matches]
        extra += [f"    guidance: Drop {entry_id}."]
    write_doc(
        repo,
        f"docs/decisions/{doc_id}.md",
        doc_id=doc_id,
        body="Retired names.",
        frontmatter_extra=extra,
    )


def _reported(repo: Path) -> list[tuple[str, int | None]]:
    return sorted(
        (finding.data["match"], finding.line)
        for finding in _findings(repo)
        if finding.data and finding.code == "retired-references/retired-reference"
    )


def test_a_retired_phrase_inside_a_longer_retired_phrase_is_reported_too(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_concept_adr(
        tmp_path,
        "0001-retire-names",
        {
            "long": ["legacy mode"],
            "short": ["legacy"],
            "outer": ["old render path"],
            "inner": ["render"],
        },
    )
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="The legacy mode is gone.\nDo not use the old render path.",
    )

    assert _reported(tmp_path) == [
        ("legacy", 10),
        ("legacy mode", 10),
        ("old render path", 11),
        ("render", 11),
    ]


def test_a_retired_phrase_is_a_whole_token_only(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_concept_adr(tmp_path, "0001-retire-names", {"mode": ["mode"], "x": ["foo bar"]})
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="model remode legacy-mode legacy_mode mode-a foo bars foo  barn xfoo bar",
    )
    write_doc(
        tmp_path,
        "docs/components/other.md",
        doc_id="other",
        body="The (MODE) switch.\nA foo\tbar.",
    )

    assert _reported(tmp_path) == [("foo bar", 11), ("mode", 10)]


@pytest.mark.parametrize(
    ("folding", "proper", "text", "expected"),
    [
        ("old way", "Topology Alpha", "TOPOLOGY ALPHA and OLD WAY.", ["old way"]),
        (
            "the old way of doing",
            "Mode B",
            "the OLD WAY of DOING and mode b.",
            ["the old way of doing"],
        ),
        ("old way", "Topology Alpha", "Topology Alpha and Old Way.", ["Topology Alpha", "old way"]),
        ("kelvin mode", "Mode B", "The \N{KELVIN SIGN}elvin mode and MODE B.", ["kelvin mode"]),
    ],
)
def test_case_folding_stays_with_its_own_phrase_when_rules_are_scanned_together(
    tmp_path: Path, folding: str, proper: str, text: str, expected: list[str]
) -> None:
    _write_config(tmp_path)
    _write_concept_adr(tmp_path, "0001-retire-names", {"folding": [folding], "proper": [proper]})
    write_doc(tmp_path, "docs/components/current.md", doc_id="current", body=text)

    assert sorted(match for match, _ in _reported(tmp_path)) == sorted(expected)


def test_a_link_to_another_record_does_not_exempt_a_phrase(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_concept_adr(tmp_path, "0001-retire-modes", {"legacy": ["legacy mode"]})
    _write_concept_adr(tmp_path, "0002-retire-sidecars", {"sidecar": ["sidecar mode"]})
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body=(
            "[legacy mode](../decisions/0002-retire-sidecars.md) and "
            "[sidecar mode](../decisions/0002-retire-sidecars.md)."
        ),
    )

    assert _reported(tmp_path) == [("legacy mode", 10)]


def test_a_citation_exempts_only_the_phrase_it_cites(tmp_path: Path) -> None:
    """The label `legacy mode` linked to its own record is a citation of that phrase. Another
    record's shorter phrase `legacy` is inside the same label, and nothing cites it."""
    _write_config(tmp_path)
    _write_concept_adr(tmp_path, "0001-retire-modes", {"legacy-mode": ["legacy mode"]})
    _write_concept_adr(tmp_path, "0002-retire-legacy", {"legacy": ["legacy"]})
    write_doc(
        tmp_path,
        "docs/components/current.md",
        doc_id="current",
        body="[legacy mode](../decisions/0001-retire-modes.md) is historical.",
    )

    assert _reported(tmp_path) == [("legacy", 10)]


def test_the_matcher_finalize_reuses_reports_every_overlapping_rule(tmp_path: Path) -> None:
    from irminsul.checks.retired_references import reported_retirements, retirement_registry

    _write_config(tmp_path)
    _write_concept_adr(
        tmp_path, "0001-retire-names", {"long": ["legacy mode"], "short": ["legacy"]}
    )
    write_doc(tmp_path, "docs/components/current.md", doc_id="current", body="Unrelated.")
    graph = load_graph(tmp_path)
    rules, _ = retirement_registry(graph)
    line = "- the legacy mode, and [legacy](../decisions/0001-retire-names.md)."

    elsewhere = reported_retirements(line, Path("docs/components/current.md"), rules)
    in_the_record = reported_retirements(line, Path("docs/decisions/0001-retire-names.md"), rules)

    assert sorted(rule.phrase for rule in elsewhere) == ["legacy", "legacy mode"]
    assert in_the_record == []
