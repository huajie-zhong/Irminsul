"""Tests for RFC lifecycle invariants."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "components").mkdir(parents=True)
    (tmp_path / "docs" / "rfcs").mkdir(parents=True)
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "test"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
        encoding="utf-8",
    )
    return tmp_path


def _write_rfc(repo: Path, *, state: str) -> Path:
    resolved = "resolved_by: docs/decisions/0001-example.md\n" if state == "implemented" else ""
    text = (
        "---\n"
        "id: 0001-example\n"
        "title: Example\n"
        ""
        f"status: {'stable' if state == 'implemented' else 'draft'}\n"
        f"rfc_state: {state}\n"
        f"{resolved}"
        "---\n\n"
        "# RFC 0001\n\nProposal.\n"
    )
    path = repo / "docs" / "rfcs" / "0001-example.md"
    path.write_text(text, encoding="utf-8")
    return path


def _findings(repo: Path):
    config = load(find_config(repo))
    return RfcLifecycleCheck().run(build_graph(repo, config))


def test_implements_backlink_before_finalization_is_an_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, state="draft")
    (repo / "docs" / "components" / "widget.md").write_text(
        "---\n"
        "id: widget\n"
        "title: Widget\n"
        ""
        "status: stable\n"
        "implements:\n"
        "  - 0001-example\n"
        "---\n\n# Widget\n",
        encoding="utf-8",
    )
    finding = next(f for f in _findings(repo) if f.category == "implements-before-implemented")
    assert finding.severity.value == "error"


def test_stable_live_doc_linking_draft_rfc_is_a_follow_through_warning(tmp_path: Path) -> None:
    from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck

    repo = _repo(tmp_path)
    _write_rfc(repo, state="draft")
    (repo / "docs" / "components" / "widget.md").write_text(
        "---\n"
        "id: widget\n"
        "title: Widget\n"
        ""
        "status: stable\n"
        "---\n\n"
        "# Widget\n\n[RFC](../rfcs/0001-example.md)\n",
        encoding="utf-8",
    )
    graph = build_graph(repo, load(find_config(repo)))
    findings = RfcFollowThroughCheck().run(graph)
    finding = next(f for f in findings if f.category == "stable-doc-links-draft-rfc")
    assert finding.severity.value == "warning"
    assert _findings(repo) == []


def test_an_implemented_rfc_needs_no_seal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs" / "decisions").mkdir()
    (repo / "docs" / "decisions" / "0001-example.md").write_text(
        "---\nid: 0001-example\ntitle: E\nstatus: stable\n---\n\n# E\n",
        encoding="utf-8",
    )
    _write_rfc(repo, state="implemented")
    assert _findings(repo) == []
    assert not hasattr(RfcLifecycleCheck(), "fixes")


def test_rfc_without_a_state_is_an_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo, state="draft")
    path.write_text(
        path.read_text(encoding="utf-8").replace("rfc_state: draft\n", ""), encoding="utf-8"
    )

    finding = next(f for f in _findings(repo) if f.category == "missing-rfc-state")

    assert finding.severity.value == "error"
    assert finding.data == {"problem": "missing-rfc-state"}
    assert "rfc_state" in (finding.suggestion or "")


def test_implemented_without_a_backlink_is_an_error(tmp_path: Path) -> None:
    """An RFC written straight to implemented passed every check, then got sealed."""
    repo = _repo(tmp_path)
    _write_rfc(repo, state="implemented")

    codes = [f.category for f in _findings(repo)]
    assert "implemented-without-evidence" in codes


def test_implemented_with_a_backlink_is_accepted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, state="implemented")
    (repo / "docs" / "components" / "widget.md").write_text(
        "---\nid: widget\ntitle: Widget\nstatus: stable\nimplements:\n  - 0001-example\n"
        "---\n\n# Widget\n",
        encoding="utf-8",
    )

    codes = [f.category for f in _findings(repo)]
    assert "implemented-without-evidence" not in codes


def test_a_no_behaviour_rfc_needs_no_backlink(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo, state="implemented")
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n## Requirements\n\nNo new behavioral requirements: a process change.\n",
        encoding="utf-8",
    )

    codes = [f.category for f in _findings(repo)]
    assert "implemented-without-evidence" not in codes
