"""Tests for RFC 0009 deterministic doc-reality audits."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.doc_reality import (
    CheckSurfaceDriftCheck,
    CliDocDriftCheck,
    ProseFileReferenceCheck,
    SchemaDocDriftCheck,
    TerminologyOverloadCheck,
)
from irminsul.config import load
from irminsul.docgraph import build_graph
from irminsul.regen.doc_surfaces import regen_doc_surfaces


def _write_config(repo: Path) -> None:
    (repo / "irminsul.toml").write_text(
        'project_name = "doc-reality"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )


def _write_doc(repo: Path, rel: str, *, doc_id: str, status: str = "stable", body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"id: {doc_id}",
                f"title: {doc_id}",
                "audience: explanation",
                "tier: 2",
                f"status: {status}",
                "describes: []",
                "---",
                "",
                f"# {doc_id}",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def _graph(repo: Path):
    return build_graph(repo, load(repo / "irminsul.toml"))


def test_prose_file_reference_flags_unlinked_md(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="See `neighbor.md` for details.",
    )

    findings = ProseFileReferenceCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "neighbor.md" in findings[0].message


def test_prose_file_reference_allows_links_and_ignores(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body=(
            "See [neighbor](neighbor.md).\n"
            "`example.md` <!-- irminsul:ignore prose-file-reference "
            'reason="example skeleton" -->'
        ),
    )

    assert ProseFileReferenceCheck().run(_graph(tmp_path)) == []


def test_prose_file_reference_allows_reference_links_definitions_and_images(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body=("See [neighbor][neighbor-doc].\n![diagram](diagram.md)\n[neighbor-doc]: neighbor.md"),
    )

    assert ProseFileReferenceCheck().run(_graph(tmp_path)) == []


def test_prose_file_reference_allows_block_ignore(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body=(
            '<!-- irminsul:ignore-start prose-file-reference reason="example skeleton" -->\n'
            "`example-a.md`\n"
            "`example-b.md`\n"
            "<!-- irminsul:ignore-end prose-file-reference -->"
        ),
    )

    assert ProseFileReferenceCheck().run(_graph(tmp_path)) == []


def test_prose_file_reference_flags_unclosed_block_ignore(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body=(
            '<!-- irminsul:ignore-start prose-file-reference reason="example skeleton" -->\n'
            "`example.md`"
        ),
    )

    findings = ProseFileReferenceCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert "without matching ignore-end" in findings[0].message


def test_generated_surface_missing_when_relevant_doc_exists(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/frontmatter.md",
        doc_id="frontmatter",
        body="See the generated reference.",
    )

    findings = SchemaDocDriftCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert "missing" in findings[0].message


def test_generated_surface_stale_after_regen(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/cli.md",
        doc_id="cli",
        body="See the generated reference.",
    )
    config = load(tmp_path / "irminsul.toml")
    regen_doc_surfaces(tmp_path, config)
    generated = tmp_path / "docs" / "40-reference" / "cli-commands.md"
    generated.write_text(generated.read_text(encoding="utf-8") + "\nextra\n", encoding="utf-8")

    findings = CliDocDriftCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert "stale" in findings[0].message


def test_generated_surface_current_after_regen(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/checks.md",
        doc_id="checks",
        body="See the generated reference.",
    )
    config = load(tmp_path / "irminsul.toml")
    regen_doc_surfaces(tmp_path, config)

    assert CheckSurfaceDriftCheck().run(_graph(tmp_path)) == []


def test_generated_surface_irrelevant_for_unrelated_repo(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="No Irminsul internals documented here.",
    )

    assert SchemaDocDriftCheck().run(_graph(tmp_path)) == []
    assert CliDocDriftCheck().run(_graph(tmp_path)) == []
    assert CheckSurfaceDriftCheck().run(_graph(tmp_path)) == []


def test_terminology_overload_flags_ambiguous_coverage(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="Coverage must stay high.",
    )

    findings = TerminologyOverloadCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert "ambiguous" in findings[0].message


def test_terminology_overload_allows_explicit_coverage(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="Source ownership coverage tracks source files claimed by docs.",
    )

    assert TerminologyOverloadCheck().run(_graph(tmp_path)) == []


def test_terminology_overload_uses_configured_rules(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "doc-reality"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["src"]',
                "[[checks.terminology_overload.rules]]",
                'term = "latency"',
                'explicit_phrases = ["p95 latency"]',
                'suggestion = "Clarify which latency metric this means."',
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="Latency must stay low.\nP95 latency is tracked separately.",
    )

    findings = TerminologyOverloadCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert findings[0].message == "'latency' is ambiguous here"
    assert findings[0].suggestion == "Clarify which latency metric this means."
