"""Tests for the UniquenessCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.uniqueness import CODE_UNDOCUMENTED_FILE, UniquenessCheck, specificity
from irminsul.config import load
from irminsul.docgraph import build_graph


def _run(repo: Path) -> list:
    cfg = load(repo / "irminsul.toml")
    graph = build_graph(repo, cfg)
    return UniquenessCheck().run(graph)


def test_specificity_ordering() -> None:
    # exact > narrower glob > broader glob
    exact = specificity("app/planner/routing/handler.py")
    narrow = specificity("app/planner/routing/*.py")
    broad = specificity("app/planner/**")
    assert exact > narrow > broad


def test_good_fixture_has_no_uniqueness_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("good"))
    assert [f for f in findings if f.severity == Severity.error] == []


def test_specificity_fixture_resolves_cleanly(
    fixture_repo: Callable[[str], Path],
) -> None:
    """Parent claims app/planner/**, child claims app/planner/routing/*.py.
    Child wins on overlapping files; no tie."""
    findings = _run(fixture_repo("specificity"))
    error_findings = [f for f in findings if f.severity == Severity.error]
    assert error_findings == []


def test_bad_uniqueness_flags_tied_claims(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-uniqueness"))
    error_findings = [f for f in findings if f.severity == Severity.error]
    error_messages = [f.message for f in error_findings]
    # Both composer-a.md and composer-b.md claim app/composer.py at identical
    # specificity → tie at most-specific level.
    assert any("app/composer.py" in m and "same specificity" in m for m in error_messages)
    assert any(f.path == Path("app/composer.py") for f in error_findings)


def test_bad_uniqueness_flags_unclaimed_in_covered_dir(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-uniqueness"))
    omissions = [f for f in findings if f.code == CODE_UNDOCUMENTED_FILE]
    # app/stranger.py lives in covered dir `app/` but no doc claims it.
    assert any("app/stranger.py" in f.message for f in omissions)
    assert any(f.path == Path("app/stranger.py") for f in omissions)
    # Unclaimed code is an error: documentation that covers a directory covers it.
    assert all(f.severity == Severity.error for f in omissions)


def test_bad_uniqueness_skips_init_py(
    fixture_repo: Callable[[str], Path],
) -> None:
    findings = _run(fixture_repo("bad-uniqueness"))
    warn_messages = [f.message for f in findings if f.severity == Severity.warning]
    # __init__.py is on the omission skip list.
    assert not any("__init__.py" in m for m in warn_messages)


def _overlap_repo(root: Path, *, link: bool) -> Path:
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    components = root / "docs" / "components"
    components.mkdir(parents=True)
    body = "\nSee [Big](big.md).\n" if link else ""
    (components / "big.md").write_text(
        "---\nid: big\ntitle: Big\nstatus: stable\ndescribes:\n  - src/**\n---\n\n# Big\n",
        encoding="utf-8",
    )
    (components / "small.md").write_text(
        "---\nid: small\ntitle: Small\nstatus: stable\ndescribes:\n  - src/a.py\n---\n\n"
        f"# Small\n{body}",
        encoding="utf-8",
    )
    return root


def test_an_overlap_between_unlinked_docs_is_a_hint(tmp_path: Path) -> None:
    findings = _run(_overlap_repo(tmp_path, link=False))
    assert [(f.code, f.path.as_posix(), f.severity) for f in findings] == [
        ("uniqueness/unlinked-overlap", "docs/components/small.md", Severity.warning)
    ]


def test_a_linked_overlap_is_fine(tmp_path: Path) -> None:
    assert _run(_overlap_repo(tmp_path, link=True)) == []
