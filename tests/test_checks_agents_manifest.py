"""Tests for AgentsManifestCheck."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.agents_manifest import AgentsManifestCheck
from irminsul.config import load
from irminsul.regen.agents_md import GENERATED_END, GENERATED_START, regen_agents_md

from .conftest import load_graph, write_doc


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
                'enabled = ["agents-manifest"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_doc(
        tmp_path,
        "docs/components/widget.md",
        doc_id="widget",
        body="A component.",
    )
    return tmp_path


def test_agents_manifest_missing(tmp_path: Path) -> None:
    _agents_repo(tmp_path)

    findings = AgentsManifestCheck().run(load_graph(tmp_path))

    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "missing" in findings[0].message


def test_agents_manifest_current_after_regen(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    regen_agents_md(repo, load(repo / "irminsul.toml"))

    assert AgentsManifestCheck().run(load_graph(repo)) == []


def test_agents_manifest_flags_drift(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    regen_agents_md(repo, load(repo / "irminsul.toml"))
    manifest = repo / "docs" / "AGENTS.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("| Summary |", "| Sum |"),
        encoding="utf-8",
    )

    findings = AgentsManifestCheck().run(load_graph(repo))

    assert len(findings) == 1
    assert "drifted" in findings[0].message


def test_agents_manifest_flags_missing_markers(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    (repo / "docs" / "AGENTS.md").write_text(
        "# Agent Navigation Manifest\n\n## Foundations\n\n## Protocol\n",
        encoding="utf-8",
    )

    findings = AgentsManifestCheck().run(load_graph(repo))

    assert any("markers" in finding.message for finding in findings)


def _scaffolded_manifest(repo: Path) -> Path:
    regen_agents_md(repo, load(repo / "irminsul.toml"))
    return repo / "docs" / "AGENTS.md"


def _generated_block(text: str) -> str:
    return text[text.index(GENERATED_START) : text.index(GENERATED_END) + len(GENERATED_END)]


def test_agents_manifest_counts_the_markers_it_found(tmp_path: Path) -> None:
    manifest = _scaffolded_manifest(_agents_repo(tmp_path))
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(GENERATED_END, ""), encoding="utf-8"
    )

    [finding] = AgentsManifestCheck().run(load_graph(tmp_path))

    assert finding.code == "agents-manifest/missing-generated-markers"
    assert "1 generated-section start and 0 end markers" in finding.message


def test_agents_manifest_refuses_a_second_generated_pair(tmp_path: Path) -> None:
    manifest = _scaffolded_manifest(_agents_repo(tmp_path))
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(f"{text}\n{_generated_block(text)}\n", encoding="utf-8")

    [finding] = AgentsManifestCheck().run(load_graph(tmp_path))

    assert finding.code == "agents-manifest/missing-generated-markers"
    assert "2 generated-section start and 2 end markers" in finding.message


def test_agents_manifest_ignores_a_fenced_example_of_the_markers(tmp_path: Path) -> None:
    manifest = _scaffolded_manifest(_agents_repo(tmp_path))
    example = f"```markdown\n{GENERATED_START}\nan example\n{GENERATED_END}\n```\n"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "## Documentation Tree", f"{example}\n## Documentation Tree"
        ),
        encoding="utf-8",
    )

    assert AgentsManifestCheck().run(load_graph(tmp_path)) == []


def test_agents_manifest_flags_missing_heading(tmp_path: Path) -> None:
    repo = _agents_repo(tmp_path)
    regen_agents_md(repo, load(repo / "irminsul.toml"))
    manifest = repo / "docs" / "AGENTS.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("## Protocol", "## Process"),
        encoding="utf-8",
    )

    findings = AgentsManifestCheck().run(load_graph(repo))

    assert len(findings) == 1
    assert "Protocol" in findings[0].message


def test_agents_manifest_unreadable_is_a_finding_not_a_traceback(tmp_path: Path) -> None:
    """A manifest that cannot be decoded, such as one saved as UTF-16, is one finding, so
    the run goes on and the other checks' findings are still reported."""
    repo = _agents_repo(tmp_path)
    regen_agents_md(repo, load(repo / "irminsul.toml"))
    manifest = repo / "docs" / "AGENTS.md"
    manifest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-16")

    findings = AgentsManifestCheck().run(load_graph(repo))

    assert [f.code for f in findings] == ["agents-manifest/manifest-unreadable"]
    assert findings[0].severity.value == "error"
