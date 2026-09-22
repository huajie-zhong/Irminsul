"""Tests for the LinksCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.links import LinksCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return LinksCheck().run(graph)


def test_good_fixture_has_no_link_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert findings == []


def test_bad_links_flags_broken_relative_targets(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-links"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]

    assert any("does-not-exist.md" in m for m in error_messages)
    assert any("nope.md" in m for m in error_messages)


def test_bad_links_skips_external_and_anchor_only(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-links"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]

    # External URLs and mailto: must NOT be flagged.
    assert not any("https://example.com" in m for m in error_messages)
    assert not any("mailto:" in m for m in error_messages)
    # Anchor-only links (no target file) must NOT be flagged.
    assert not any(m.endswith("'#linker'") for m in error_messages)


def test_bad_links_resolves_through_anchors(
    fixture_repo: Callable[[str], Path],
) -> None:
    """A link like `[x](neighbor.md#heading)` should resolve to neighbor.md
    (which exists) — i.e. NOT flagged."""
    findings = _run(fixture_repo("bad-links"))
    error_messages = [f.message for f in findings if f.severity == Severity.error]
    # neighbor.md exists, so the anchor variant must not be a broken link.
    # We only check that the existing file's anchored form isn't flagged.
    assert not any("neighbor.md#heading" in m for m in error_messages)


def test_guidance_files_check_anchors_into_docs_and_themselves(tmp_path: Path) -> None:
    (tmp_path / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n', encoding="utf-8"
    )
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir()
    doc.write_text(
        "---\nid: guide\ntitle: G\nstatus: stable\n---\n\n# Guide\n\n## Setup\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "# Agents\n\n## Loop\n\n[ok](docs/guide.md#setup) [bad](docs/guide.md#install)\n"
        "[self](#loop) [missing](#nowhere)\n",
        encoding="utf-8",
    )
    findings = [f for f in _run(tmp_path) if f.path == Path("AGENTS.md")]
    assert sorted(f.data["anchor"] for f in findings) == ["install", "nowhere"]
    assert {f.code for f in findings} == {"links/unknown-anchor"}
