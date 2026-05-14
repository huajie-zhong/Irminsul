"""Tests for RFC 0009 deterministic doc-reality audits."""

from __future__ import annotations

import time
from pathlib import Path

from git import Repo

from irminsul.checks.doc_reality import (
    AgentsManifestCheck,
    CheckSurfaceDriftCheck,
    ClaimProvenanceCheck,
    CliDocDriftCheck,
    ProseFileReferenceCheck,
    SchemaDocDriftCheck,
    TerminologyOverloadCheck,
)
from irminsul.config import load
from irminsul.docgraph import build_graph
from irminsul.regen.agents_md import regen_agents_md
from irminsul.regen.doc_surfaces import regen_doc_surfaces


def _write_config(repo: Path) -> None:
    (repo / "irminsul.toml").write_text(
        'project_name = "doc-reality"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )


def _write_doc(
    repo: Path,
    rel: str,
    *,
    doc_id: str,
    status: str = "stable",
    body: str,
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
                "audience: explanation",
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


def _graph(repo: Path):
    return build_graph(repo, load(repo / "irminsul.toml"))


def _init_repo(root: Path) -> Repo:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    return repo


def _commit(repo: Repo, rel_path: str, content: str, message: str) -> None:
    fp = Path(repo.working_dir) / rel_path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    repo.index.add([rel_path])
    repo.index.commit(message)


def test_claim_provenance_accepts_valid_claim_states(tmp_path: Path) -> None:
    _write_config(tmp_path)
    (tmp_path / "src" / "checks").mkdir(parents=True)
    (tmp_path / "src" / "checks" / "claim.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "action.yml").write_text("name: docs\n", encoding="utf-8")
    _write_doc(
        tmp_path,
        "docs/20-components/claim-check.md",
        doc_id="claim-check",
        body="Implementation docs.",
    )
    _write_doc(
        tmp_path,
        "docs/40-reference/checks.md",
        doc_id="checks",
        body="Enablement docs.",
    )
    _write_doc(
        tmp_path,
        "docs/80-evolution/rfcs/0001-thing.md",
        doc_id="0001-thing",
        status="draft",
        body="Future work.",
        frontmatter_extra=["rfc_state: open"],
    )
    _write_doc(
        tmp_path,
        "docs/00-foundation/enforcement.md",
        doc_id="enforcement",
        body=(
            "CI blocks invalid docs. <!-- claim:enabled-claim -->\n\n"
            "A planned feature exists. <!-- claim:planned-claim -->"
        ),
        frontmatter_extra=[
            "claims:",
            "  - id: planned-claim",
            "    state: planned",
            "    kind: feature",
            "    claim: Planned feature.",
            "    evidence:",
            "      - docs/80-evolution/rfcs/0001-thing.md",
            "  - id: implemented-claim",
            "    state: implemented",
            "    kind: check",
            "    claim: Source exists.",
            "    evidence:",
            "      - src/checks/claim.py",
            "  - id: available-claim",
            "    state: available",
            "    kind: check",
            "    claim: Source and docs exist.",
            "    evidence:",
            "      - src/checks/claim.py",
            "      - docs/40-reference/checks.md",
            "  - id: enabled-claim",
            "    state: enabled",
            "    kind: ci_gate",
            "    claim: Workflow evidence exists.",
            "    evidence:",
            "      - action.yml",
            "  - id: external-claim",
            "    state: external",
            "    kind: local_tool",
            "    claim: External config exists.",
            "    evidence:",
            "      - action.yml",
        ],
    )

    assert ClaimProvenanceCheck().run(_graph(tmp_path)) == []


def test_claim_provenance_flags_state_inappropriate_evidence(tmp_path: Path) -> None:
    _write_config(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "claim.py").write_text("x = 1\n", encoding="utf-8")
    _write_doc(
        tmp_path,
        "docs/00-foundation/enforcement.md",
        doc_id="enforcement",
        body="CI blocks invalid docs. <!-- claim:enabled-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: enabled-claim",
            "    state: enabled",
            "    kind: ci_gate",
            "    claim: Workflow evidence exists.",
            "    evidence:",
            "      - src/claim.py",
        ],
    )

    findings = ClaimProvenanceCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "state 'enabled'" in findings[0].message


def test_claim_provenance_warns_on_risky_prose_without_reference(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/00-foundation/enforcement.md",
        doc_id="enforcement",
        body="CI automatically rewrites old docs.",
    )

    findings = ClaimProvenanceCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert findings[0].severity.value == "warning"
    assert "high-risk" in findings[0].message


def test_claim_provenance_warns_on_unknown_claim_reference(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/00-foundation/enforcement.md",
        doc_id="enforcement",
        body="CI blocks invalid docs. <!-- claim:missing -->",
    )

    findings = ClaimProvenanceCheck().run(_graph(tmp_path))

    assert any("unknown structured claim reference" in finding.message for finding in findings)


def test_claim_provenance_warns_on_resolved_planned_rfc(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_doc(
        tmp_path,
        "docs/50-decisions/0001-thing.md",
        doc_id="0001-thing-decision",
        body="Accepted.",
    )
    _write_doc(
        tmp_path,
        "docs/80-evolution/rfcs/0001-thing.md",
        doc_id="0001-thing",
        status="draft",
        body="Future work.",
        frontmatter_extra=[
            "rfc_state: accepted",
            "resolved_by: docs/50-decisions/0001-thing.md",
        ],
    )
    _write_doc(
        tmp_path,
        "docs/00-foundation/enforcement.md",
        doc_id="enforcement",
        body="A planned feature exists. <!-- claim:planned-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: planned-claim",
            "    state: planned",
            "    kind: feature",
            "    claim: Planned feature.",
            "    evidence:",
            "      - docs/80-evolution/rfcs/0001-thing.md",
        ],
    )

    findings = ClaimProvenanceCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert "resolved RFC" in findings[0].message


def test_claim_provenance_warns_when_evidence_changed_after_doc(tmp_path: Path) -> None:
    _write_config(tmp_path)
    repo = _init_repo(tmp_path)
    _commit(repo, "irminsul.toml", (tmp_path / "irminsul.toml").read_text(), "config")
    _commit(
        repo,
        "action.yml",
        "name: docs\n",
        "workflow",
    )
    _write_doc(
        tmp_path,
        "docs/00-foundation/enforcement.md",
        doc_id="enforcement",
        body="CI blocks invalid docs. <!-- claim:enabled-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: enabled-claim",
            "    state: enabled",
            "    kind: ci_gate",
            "    claim: Workflow evidence exists.",
            "    evidence:",
            "      - action.yml",
        ],
    )
    repo.index.add(["docs/00-foundation/enforcement.md"])
    repo.index.commit("doc claim")
    time.sleep(1.1)
    _commit(repo, "action.yml", "name: docs\non: [push]\n", "workflow update")

    findings = ClaimProvenanceCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert "changed after the doc" in findings[0].message


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


def _agents_repo(tmp_path: Path) -> Path:
    # Opt in to `agents-manifest` so a missing manifest is treated as an error.
    (tmp_path / "irminsul.toml").write_text(
        "\n".join(
            [
                'project_name = "agents"',
                "[paths]",
                'docs_root = "docs"',
                'source_roots = ["src"]',
                "[checks]",
                'hard = ["agents-manifest"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_doc(
        tmp_path,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="A component.",
    )
    return tmp_path


def test_agents_manifest_missing(tmp_path: Path) -> None:
    _agents_repo(tmp_path)

    findings = AgentsManifestCheck().run(_graph(tmp_path))

    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "missing" in findings[0].message


def test_agents_manifest_current_after_regen(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    regen_agents_md(repo, load(repo / "irminsul.toml"))

    assert AgentsManifestCheck().run(_graph(repo)) == []


def test_agents_manifest_flags_drift(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    regen_agents_md(repo, load(repo / "irminsul.toml"))
    manifest = repo / "docs" / "AGENTS.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("| Audience |", "| Aud |"),
        encoding="utf-8",
    )

    findings = AgentsManifestCheck().run(_graph(repo))

    assert len(findings) == 1
    assert "drifted" in findings[0].message


def test_agents_manifest_flags_missing_markers(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    (repo / "docs" / "AGENTS.md").write_text(
        "# Agent Navigation Manifest\n\n## Foundations\n\n## Protocol\n",
        encoding="utf-8",
    )

    findings = AgentsManifestCheck().run(_graph(repo))

    assert any("markers" in finding.message for finding in findings)


def test_agents_manifest_flags_missing_heading(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    regen_agents_md(repo, load(repo / "irminsul.toml"))
    manifest = repo / "docs" / "AGENTS.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("## Protocol", "## Process"),
        encoding="utf-8",
    )

    findings = AgentsManifestCheck().run(_graph(repo))

    assert len(findings) == 1
    assert "Protocol" in findings[0].message


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
