"""Tests for RFC lifecycle invariants."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck

from .conftest import load_graph, run_check, write_config, write_doc


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "components").mkdir(parents=True)
    (tmp_path / "docs" / "rfcs").mkdir(parents=True)
    write_config(tmp_path, project_name="test")
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
    return run_check(RfcLifecycleCheck, repo)


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
    finding = next(
        f for f in _findings(repo) if f.code == "rfc-lifecycle/implements-before-implemented"
    )
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
    findings = run_check(RfcFollowThroughCheck, repo)
    finding = next(f for f in findings if f.code == "rfc-follow-through/stable-doc-links-draft-rfc")
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

    finding = next(f for f in _findings(repo) if f.code == "rfc-lifecycle/missing-rfc-state")

    assert finding.severity.value == "error"
    assert finding.data is None
    assert "rfc_state" in (finding.suggestion or "")


def test_implemented_without_a_backlink_is_an_error(tmp_path: Path) -> None:
    """An RFC written straight to implemented passed every check, then got sealed."""
    repo = _repo(tmp_path)
    _write_rfc(repo, state="implemented")

    codes = [f.code for f in _findings(repo)]
    assert "rfc-lifecycle/implemented-without-evidence" in codes


def test_implemented_with_a_backlink_is_accepted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_rfc(repo, state="implemented")
    (repo / "docs" / "components" / "widget.md").write_text(
        "---\nid: widget\ntitle: Widget\nstatus: stable\nimplements:\n  - 0001-example\n"
        "---\n\n# Widget\n",
        encoding="utf-8",
    )

    codes = [f.code for f in _findings(repo)]
    assert "rfc-lifecycle/implemented-without-evidence" not in codes


def test_a_no_behaviour_rfc_needs_no_backlink(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _write_rfc(repo, state="implemented")
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n## Requirements\n\nNo new behavioral requirements: a process change.\n",
        encoding="utf-8",
    )

    codes = [f.code for f in _findings(repo)]
    assert "rfc-lifecycle/implemented-without-evidence" not in codes


def test_a_backslash_resolved_by_names_the_record_on_every_platform(tmp_path: Path) -> None:
    """The change commands read `\\` as a separator and `rfc-lifecycle` did not, so on Linux
    a Windows-written `resolved_by` passed `change transition` and failed `irminsul check`."""
    from irminsul.change.gate import dangling_resolved_by
    from irminsul.frontmatter import RfcStateEnum

    repo = _repo(tmp_path)
    write_doc(repo, "docs/decisions/0001-record.md", doc_id="0001-record", body="A record.")
    (repo / "docs" / "rfcs" / "0001-example.md").write_text(
        "---\nid: 0001-example\ntitle: Example\nstatus: stable\nrfc_state: accepted\n"
        "resolved_by: 'docs\\decisions\\0001-record.md'\n---\n\n# RFC 0001\n\nProposal.\n",
        encoding="utf-8",
    )
    graph = load_graph(repo)
    rfc = graph.nodes["0001-example"]

    assert graph.doc_at("docs\\decisions\\0001-record.md") is graph.nodes["0001-record"]
    assert (
        dangling_resolved_by(graph, rfc, RfcStateEnum.accepted, rfc.frontmatter.resolved_by) is None
    )
    assert "rfc-lifecycle/dangling-resolved-by" not in {f.code for f in _findings(repo)}
