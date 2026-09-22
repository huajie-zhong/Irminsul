"""Tests for GlossaryDisciplineCheck.fixes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.glossary import GlossaryDisciplineCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.fix import apply_fixes


def _fixes(repo: Path) -> list:
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    check = GlossaryDisciplineCheck()
    return check.fixes(check.run(graph), graph)


def test_autolink_requires_confirm_and_wraps_first_use(
    fixture_repo: Callable[[str], Path],
) -> None:
    repo = fixture_repo("soft-glossary")
    fixes = _fixes(repo)
    benign = repo / "docs" / "components" / "benign.md"

    benign_fixes = [f for f in fixes if f.path == Path("docs/components/benign.md")]
    assert len(benign_fixes) == 1
    assert benign_fixes[0].requires_confirm is True

    before = benign.read_text(encoding="utf-8")
    apply_fixes(repo, fixes, dry_run=False, confirm=False)
    assert benign.read_text(encoding="utf-8") == before  # held

    apply_fixes(repo, fixes, dry_run=False, confirm=True)
    text = benign.read_text(encoding="utf-8")
    assert "[Composer](../GLOSSARY.md#composer)" in text


def test_autolink_is_idempotent(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("soft-glossary")
    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=True)
    benign = repo / "docs" / "components" / "benign.md"
    once = benign.read_text(encoding="utf-8")

    # Second pass must not double-wrap the now-linked term.
    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=True)
    assert benign.read_text(encoding="utf-8") == once
    assert once.count("](../GLOSSARY.md#composer)") == 1


def test_autolink_never_writes_into_an_html_comment(
    fixture_repo: Callable[[str], Path],
) -> None:
    """An anchor marker is an HTML comment holding a path, and the masker did not cover
    comments — so when the earliest occurrence of a term sat inside one, auto-linking
    rewrote the anchor's path into a markdown link, destroying the seal and turning a
    green tree red.

    The same injection lands in an `irminsul:ignore ... reason="..."` comment.
    """
    repo = fixture_repo("soft-glossary")
    doc = repo / "docs" / "components" / "sealed.md"
    marker = "<!-- anchor: app/Composer/mod.py#run -->"
    ignore = '<!-- irminsul:ignore reality reason="Composer is quoted here" -->'
    doc.write_text(
        "---\nid: sealed\ntitle: Sealed\nstatus: stable\ndescribes: []\n---\n\n"
        f"# Sealed\n\n{marker}\n{ignore}\n\nThe Composer runs the pipeline.\n\n"
        "## Scope & Limitations\n\nNothing else.\n",
        encoding="utf-8",
    )

    apply_fixes(repo, _fixes(repo), dry_run=False, confirm=True)
    text = doc.read_text(encoding="utf-8")

    assert marker in text, "the anchor marker was rewritten"
    assert ignore in text, "the ignore comment's reason was rewritten"
    # The prose occurrence is still linked, so masking comments did not disable the fix.
    assert "[Composer](../GLOSSARY.md#composer)" in text
