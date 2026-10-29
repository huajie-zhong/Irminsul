"""Tests for the LinksCheck."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.links import LinksCheck

from .conftest import git_init, run_check, write, write_config


def _run(repo: Path) -> list:
    return run_check(LinksCheck, repo)


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
    write_config(tmp_path)
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


def test_a_links_line_is_where_it_stands_in_the_body() -> None:
    from irminsul.docgraph_index import links_of, parse_markdown

    body = (
        "Intro [a](https://a.example/)\n"
        'wraps and `code span` then <span\nclass="x">z</span> [b](https://b.example/)\n'
        "\n"
        "> quoted\n"
        "> with [c](https://c.example/)\n"
        "\n"
        "- item\n"
        "  continued [d][ref]\n"
        "\n"
        "```\n"
        "[fenced](https://fenced.example/)\n"
        "```\n"
        "\n"
        "<https://e.example/>\n"
        "\n"
        "[ref]: https://d.example/\n"
    )

    assert [(link.href, link.line) for link in links_of(parse_markdown(body))] == [
        ("https://a.example/", 1),
        ("https://b.example/", 3),
        ("https://c.example/", 6),
        ("https://d.example/", 9),
        ("https://e.example/", 15),
    ]


def _doc(repo: Path, rel: str, body: str) -> None:
    doc_id = Path(rel).stem.replace(" ", "-")
    write(
        repo,
        rel,
        f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\nsummary: s.\n---\n\n{body}",
    )


def _link_repo(tmp_path: Path) -> Path:
    write_config(tmp_path)
    return tmp_path


def test_a_finding_carries_the_line_of_its_link(tmp_path: Path) -> None:
    repo = _link_repo(tmp_path)
    _doc(
        repo,
        "docs/guide.md",
        "# Guide\n\nA paragraph that wraps\nonto a second line and then points at\n"
        "[nowhere](nowhere.md) and [no heading](#missing).\n",
    )

    findings = _run(repo)

    assert sorted((f.code, f.line) for f in findings) == [
        ("links/broken-link", 12),
        ("links/unknown-anchor", 12),
    ]


def test_a_link_in_an_anchor_tag_is_checked(tmp_path: Path) -> None:
    repo = _link_repo(tmp_path)
    _doc(
        repo,
        "docs/guide.md",
        '# Guide\n\nSee <a href=\'other.md\'>other</a>, <a\nclass="x" href="gone.md#top">gone</a>,'
        ' <a href="https://example.com">out</a> and <a href="#nowhere">here</a>.\n',
    )
    _doc(repo, "docs/other.md", "# Other\n")

    findings = _run(repo)

    assert sorted((f.code, f.line) for f in findings) == [
        ("links/broken-link", 11),
        ("links/unknown-anchor", 11),
    ]


def test_a_percent_encoded_link_names_the_file_it_decodes_to(tmp_path: Path) -> None:
    repo = _link_repo(tmp_path)
    _doc(repo, "docs/guide.md", "# Guide\n\n[spaced](my%20notes.md) [absent](no%20file.md)\n")
    _doc(repo, "docs/my notes.md", "# Notes\n")

    assert [f.data["resolved"] for f in _run(repo)] == ["docs/no file.md"]


def test_a_link_starting_with_a_slash_starts_at_the_repository_root(tmp_path: Path) -> None:
    repo = _link_repo(tmp_path)
    _doc(
        repo,
        "docs/components/guide.md",
        "# Guide\n\n[root](/docs/other.md) [absent](/docs/absent.md)\n",
    )
    _doc(repo, "docs/other.md", "# Other\n")

    assert [f.data["resolved"] for f in _run(repo)] == ["docs/absent.md"]


def test_a_link_cannot_climb_above_the_repository_root(tmp_path: Path) -> None:
    repo = _link_repo(tmp_path / "repo")
    _doc(repo, "docs/guide.md", "# Guide\n\n[out](../../outside.md) [in](../README.md)\n")
    write(repo, "README.md", "# Repo\n")
    write(repo, "outside.md", "# At the root\n")
    write(tmp_path, "outside.md", "# Beside the repo\n")

    findings = _run(repo)

    assert [(f.code, f.message) for f in findings] == [
        ("links/broken-link", "broken link: '../../outside.md' (leaves the repository)")
    ]
    assert "full URL" in (findings[0].suggestion or "")
    assert "code span" in (findings[0].suggestion or "")


def test_a_link_to_a_missing_file_inside_the_repository_has_no_such_remedy(
    tmp_path: Path,
) -> None:
    repo = _link_repo(tmp_path)
    _doc(repo, "docs/guide.md", "# Guide\n\n[gone](gone.md)\n")

    [finding] = _run(repo)

    assert finding.suggestion is None


def test_a_heading_is_linked_by_the_anchor_github_gives_it(tmp_path: Path) -> None:
    repo = _link_repo(tmp_path)
    _doc(
        repo,
        "docs/guide.md",
        "# Guide\n\n## Scope & Limitations\n\n## Notes\n\n## Notes\n\n## Café\n\n"
        "[amp](#scope--limitations) [again](#notes-1) [accent](#caf%C3%A9)\n"
        "[across](other.md#scope--limitations)\n",
    )
    _doc(repo, "docs/other.md", "# Other\n\n## Scope & Limitations\n")

    assert _run(repo) == []


def test_the_anchor_a_collapsing_slugger_gave_an_ampersand_heading_is_unknown(
    tmp_path: Path,
) -> None:
    repo = _link_repo(tmp_path)
    _doc(
        repo,
        "docs/guide.md",
        "# Guide\n\n## Scope & Limitations\n\n## Notes\n\n[old](#scope-limitations) [one](#notes-1)\n",
    )

    assert sorted(f.data["anchor"] for f in _run(repo)) == ["notes-1", "scope-limitations"]


def test_a_guidance_file_links_a_heading_by_the_anchor_github_gives_it(tmp_path: Path) -> None:
    write_config(tmp_path)
    _doc(tmp_path, "docs/guide.md", "# Guide\n\n## Scope & Limitations\n")
    write(
        tmp_path,
        "AGENTS.md",
        "# Agents\n\n## Rules & Notes\n\n"
        "[doc](docs/guide.md#scope--limitations) [self](#rules--notes)\n",
    )

    assert [f for f in _run(tmp_path) if f.path == Path("AGENTS.md")] == []


def _siblings(tmp_path: Path, *, checkout: bool = True) -> Path:
    code = tmp_path / "code"
    if checkout:
        git_init(code)
    write(code, "src/cli.py", "def main() -> None:\n    pass\n")
    write(code, "my notes.md", "# Notes\n\n## Setup\n")
    write(
        code,
        "README.md",
        "# Code\n\n[cli](src/cli.py) [missing](src/gone.py) [notes](my%20notes.md#setup)\n"
        "[docs repo](../docs/README.md) [above](../../elsewhere.md) [root](/src/gone.py)\n",
    )
    docs = tmp_path / "docs"
    git_init(docs)
    write(docs, "README.md", "# Docs\n")
    write_config(docs, extra='extra_docs = ["README.md", "../code/README.md"]\n')
    return docs


def test_a_sibling_repositorys_readme_is_judged_by_its_own_root(tmp_path: Path) -> None:
    docs = _siblings(tmp_path)

    findings = [f for f in _run(docs) if f.path == Path("../code/README.md")]

    assert sorted((f.line, f.message) for f in findings) == [
        (3, "broken link: 'src/gone.py' (resolved to '../code/src/gone.py')"),
        (4, "broken link: '../../elsewhere.md' (leaves the repository)"),
        (4, "broken link: '../docs/README.md' (leaves the repository)"),
    ]


def test_a_readme_outside_any_git_checkout_sets_no_limit(tmp_path: Path) -> None:
    docs = _siblings(tmp_path, checkout=False)

    findings = [f for f in _run(docs) if f.path == Path("../code/README.md")]

    assert sorted((f.line, f.message) for f in findings) == [
        (3, "broken link: 'src/gone.py' (resolved to '../code/src/gone.py')"),
        (4, "broken link: '../../elsewhere.md' (resolved to '../../elsewhere.md')"),
    ]
