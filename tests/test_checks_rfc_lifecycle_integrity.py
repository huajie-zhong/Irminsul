"""Tests for RFC lifecycle drift and frozen-record enforcement."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.rfc_lifecycle_integrity import RfcLifecycleIntegrityCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.fix import apply_fixes
from irminsul.rfc_freeze import seal_text


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "20-components").mkdir(parents=True)
    (tmp_path / "docs" / "80-evolution" / "rfcs").mkdir(parents=True)
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "test"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
        encoding="utf-8",
    )
    return tmp_path


def _write_rfc(repo: Path, *, state: str, seal: bool = False) -> Path:
    resolved = "resolved_by: docs/50-decisions/0001-example.md\n" if state == "implemented" else ""
    text = (
        "---\n"
        "id: 0001-example\n"
        "title: Example\n"
        "audience: explanation\n"
        "tier: 2\n"
        f"status: {'stable' if state == 'implemented' else 'draft'}\n"
        f"rfc_state: {state}\n"
        f"{resolved}"
        "---\n\n"
        "# RFC 0001\n\nProposal.\n"
    )
    if seal:
        text = seal_text(text)
    path = repo / "docs" / "80-evolution" / "rfcs" / "0001-example.md"
    path.write_text(text, encoding="utf-8")
    return path


def _findings(repo: Path):
    config = load(find_config(repo))
    return RfcLifecycleIntegrityCheck().run(build_graph(repo, config))


def test_implemented_rfc_without_seal_is_fixable_warning(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo, state="implemented")
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    check = RfcLifecycleIntegrityCheck()
    findings = check.run(graph)
    [finding] = [f for f in findings if f.category == "missing-frozen-hash"]
    assert finding.severity.value == "warning"

    result = apply_fixes(repo, check.fixes(findings, graph), dry_run=False, confirm=True)
    assert result.errors == []
    assert 'frozen_hash: "sha256:' in path.read_text(encoding="utf-8")
    assert _findings(repo) == []


def test_editing_frozen_rfc_is_an_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo, state="implemented", seal=True)
    path.write_text(
        path.read_text(encoding="utf-8").replace("Proposal.", "Extended proposal."),
        encoding="utf-8",
    )
    finding = next(f for f in _findings(repo) if f.category == "frozen-content-changed")
    assert finding.severity.value == "error"
    assert finding.data is not None and finding.data["expected"] != finding.data["actual"]


def test_seal_on_draft_rfc_is_an_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, state="draft", seal=True)
    finding = next(f for f in _findings(repo) if f.category == "premature-frozen-hash")
    assert finding.severity.value == "error"


def test_implements_backlink_before_finalization_is_an_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, state="draft")
    (repo / "docs" / "20-components" / "widget.md").write_text(
        "---\n"
        "id: widget\n"
        "title: Widget\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "implements:\n"
        "  - 0001-example\n"
        "---\n\n# Widget\n",
        encoding="utf-8",
    )
    finding = next(
        f for f in _findings(repo) if f.category == "implementation-evidence-before-finalization"
    )
    assert finding.severity.value == "error"


def test_stable_live_doc_linking_draft_rfc_is_a_warning(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, state="draft")
    (repo / "docs" / "20-components" / "widget.md").write_text(
        "---\n"
        "id: widget\n"
        "title: Widget\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "---\n\n"
        "# Widget\n\n[RFC](../80-evolution/rfcs/0001-example.md)\n",
        encoding="utf-8",
    )
    finding = next(f for f in _findings(repo) if f.category == "stable-doc-links-draft-rfc")
    assert finding.severity.value == "warning"


def test_pre_lifecycle_rfc_is_a_migration_warning(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo, state="draft")
    path.write_text(
        path.read_text(encoding="utf-8").replace("rfc_state: draft\n", ""), encoding="utf-8"
    )

    finding = next(f for f in _findings(repo) if f.category == "pre-lifecycle-rfc")

    assert finding.severity.value == "warning"
    assert finding.data == {"problem": "pre-lifecycle-rfc", "rfc": "0001-example"}
    assert "change migrate 0001-example" in (finding.suggestion or "")
