"""Tests for SupersessionCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.supersession import SupersessionCheck

from .conftest import check_fixes, run_check, write_config, write_doc


def _findings(repo: Path) -> list:
    return run_check(SupersessionCheck, repo)


def test_missing_deprecated_status_warned(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-supersession")
    findings = _findings(repo)
    msgs = [f.message for f in findings]
    assert any("status is" in m for m in msgs)


def test_unknown_supersedes_id_errors() -> None:
    """Direct unit: build a tiny graph with a dangling supersedes pointer."""

    from irminsul.checks.base import Severity
    from irminsul.docgraph import DocGraph, DocNode
    from irminsul.frontmatter import DocFrontmatter, StatusEnum

    fm = DocFrontmatter(
        id="x",
        title="X",
        status=StatusEnum.stable,
        supersedes=["does-not-exist"],
    )
    node = DocNode(id="x", path=Path("x.md"), frontmatter=fm, body="")
    graph = DocGraph(nodes={"x": node}, by_path={Path("x.md"): node})

    findings = SupersessionCheck().run(graph)
    assert any(f.severity == Severity.error for f in findings)
    assert any("does-not-exist" in f.message for f in findings)


def _rfc_repo(root: Path) -> Path:
    """An implemented RFC, a draft RFC superseding it, and a component superseding it."""
    for rel, frontmatter in (
        (
            "docs/rfcs/0001-base.md",
            "id: 0001-base\ntitle: Base\nstatus: stable\nrfc_state: implemented\n"
            "resolved_by: docs/components/component.md\n",
        ),
        (
            "docs/rfcs/0002-next.md",
            "id: 0002-next\ntitle: Next\nstatus: draft\nrfc_state: draft\n"
            "supersedes: [0001-base]\n",
        ),
        (
            "docs/components/component.md",
            "id: component\ntitle: Component\nstatus: stable\nsupersedes: [0001-base]\n",
        ),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{frontmatter}---\n\n# Doc\n", encoding="utf-8")
    write_config(root)
    return root


def test_supersession_leaves_an_rfc_predecessor_alone(tmp_path: Path) -> None:
    """An implemented RFC does not change, so neither a successor RFC nor a component that
    supersedes it can ask for its status to be rewritten."""
    assert _findings(_rfc_repo(tmp_path)) == []


def _superseded_repo(root: Path, old_status: str) -> Path:
    write_config(root)
    write_doc(root, "docs/components/old.md", doc_id="old", body="Old.", status=old_status)
    write_doc(
        root,
        "docs/components/new.md",
        doc_id="new",
        body="New.",
        frontmatter_extra=["supersedes: [old]"],
    )
    return root


def test_a_superseded_doc_may_be_deprecated_or_removed(tmp_path: Path) -> None:
    """`stale-reaper` asks an aged deprecated doc to be removed, so `removed` has to satisfy
    the check that asked for `deprecated`, and `fix` must leave it alone."""
    for status in ("deprecated", "removed"):
        repo = _superseded_repo(tmp_path / status, status)

        assert _findings(repo) == []
        assert check_fixes(SupersessionCheck, repo) == []


def test_a_superseded_doc_still_live_is_reported_and_deprecated_by_fix(tmp_path: Path) -> None:
    for status in ("stable", "draft"):
        repo = _superseded_repo(tmp_path / status, status)

        assert [f.code for f in _findings(repo)] == ["supersession/status-not-deprecated"]
        assert [fix.description for fix in check_fixes(SupersessionCheck, repo)] == [
            "set status: deprecated in docs/components/old.md"
        ]
