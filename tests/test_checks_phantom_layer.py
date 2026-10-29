"""Tests for PhantomLayerCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks.base import Severity
from irminsul.checks.phantom_layer import PhantomLayerCheck

from .conftest import run_check, write_config, write_doc


def _findings(repo: Path) -> list:
    return run_check(PhantomLayerCheck, repo)


def test_good_fixture_has_no_phantom_findings(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    findings = _findings(repo)
    assert findings == []


def test_hollow_stable_directory_is_an_error(fixture_repo: Callable[[str], Path]) -> None:
    """A hollow layer whose INDEX is `stable` is an error."""
    repo = fixture_repo("bad-phantom")
    errors = [f for f in _findings(repo) if f.severity == Severity.error]
    assert len(errors) == 1
    assert "phantom layer" in errors[0].message
    assert "guides" in errors[0].message


def test_finding_has_path(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-phantom")
    findings = _findings(repo)
    assert findings
    for f in findings:
        assert f.path is not None
        assert str(f.path).endswith("INDEX.md")


def test_draft_index_downgrades_to_info(fixture_repo: Callable[[str], Path]) -> None:
    """A hollow `status: draft` layer is reported as info, not a warning.

    The fixture has two hollow layers: `guides` (stable INDEX, warning)
    and `operations` (draft INDEX, info — under construction, non-gating).
    """
    findings = _findings(fixture_repo("bad-phantom"))
    infos = [f for f in findings if f.severity == Severity.info]
    assert len(infos) == 1
    assert "operations" in infos[0].message
    assert "under construction" in infos[0].message
    # The draft layer never produces a gating warning.
    assert all("operations" not in f.message for f in findings if f.severity == Severity.warning)


def test_a_hollow_layer_is_found_whatever_way_docs_root_is_spelled(
    fixture_repo: Callable[[str], Path],
) -> None:
    """`docs_root = "/docs"` is a valid spelling of the folder `docs`; the check reads the
    tree the graph walked, not the raw field, which `/` would turn into the filesystem root."""
    repo = fixture_repo("bad-phantom")
    expected = sorted(f.message for f in _findings(repo))
    toml = repo / "irminsul.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('docs_root = "docs"', 'docs_root = "/docs"'),
        encoding="utf-8",
    )

    assert expected
    assert sorted(f.message for f in _findings(repo)) == expected


def test_a_layer_whose_only_content_doc_has_no_frontmatter_is_not_hollow(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The broken doc is `frontmatter`'s to report; calling its folder hollow as well would
    name one mistake twice."""
    repo = fixture_repo("bad-phantom")
    (repo / "docs" / "guides" / "intro.md").write_text("# no frontmatter\n", encoding="utf-8")

    assert all("guides" not in f.message for f in _findings(repo))


def _layer_repo(tmp_path: Path, *docs: tuple[str, str]) -> Path:
    write_config(tmp_path, enabled=["phantom-layer"])
    for rel, doc_id in docs:
        write_doc(tmp_path, rel, doc_id=doc_id, body="Text.")
    return tmp_path


def test_a_layer_whose_docs_live_in_subfolders_is_not_hollow(tmp_path: Path) -> None:
    repo = _layer_repo(
        tmp_path,
        ("docs/components/INDEX.md", "components"),
        ("docs/components/checks/INDEX.md", "checks"),
        ("docs/components/checks/links.md", "links"),
        ("docs/components/checks/deep/more/anchors.md", "anchors"),
    )

    assert _findings(repo) == []


def test_a_layer_holding_only_index_files_below_it_is_still_hollow(tmp_path: Path) -> None:
    repo = _layer_repo(
        tmp_path,
        ("docs/components/INDEX.md", "components"),
        ("docs/components/checks/INDEX.md", "checks"),
        ("docs/guides/INDEX.md", "guides"),
        ("docs/guides/intro.md", "intro"),
    )

    assert sorted(f.message for f in _findings(repo)) == [
        "phantom layer: 'docs/components' has only INDEX.md and no content docs",
        "phantom layer: 'docs/components/checks' has only INDEX.md and no content docs",
    ]
