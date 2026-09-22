"""Ignore comments suppress soft-check findings on the lines they cover."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()


def _repo(root: Path, body: str) -> Path:
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["frontmatter", "reality"]\n',
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "store.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        f"---\nid: store\ntitle: Store\nstatus: stable\n---\n\n# Store\n\n{body}",
        encoding="utf-8",
    )
    return root


def _codes(root: Path) -> list[str]:
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root)])
    return sorted(f["code"] for f in json.loads(result.output)["findings"])


def test_a_comment_suppresses_its_own_line(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        'The store previously used SQLite. <!-- irminsul:ignore reality reason="quoted" -->\n'
        "It then used the roadmap.\n",
    )
    assert _codes(root) == ["reality/speculative-language"]


def test_a_standalone_comment_covers_the_next_line_and_codes_match(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        '<!-- irminsul:ignore reality/history-narration reason="quoted" -->\n\n'
        "The store previously used SQLite.\n",
    )
    assert _codes(root) == []


def test_a_block_covers_every_line_inside_it(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        '<!-- irminsul:ignore-start reality reason="quoted" -->\n'
        "Previously A.\n\nThe roadmap says B.\n"
        "<!-- irminsul:ignore-end reality -->\nPreviously C.\n",
    )
    assert _codes(root) == ["reality/history-narration"]


def test_misused_comments_are_reported(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        'Plain text. <!-- irminsul:ignore reality reason="suppresses nothing" -->\n\n'
        'Previously A. <!-- irminsul:ignore links reason="certain code" -->\n\n'
        'Text. <!-- irminsul:ignore nonsense reason="unknown check" -->\n\n'
        '<!-- irminsul:ignore-start reality reason="never closed" -->\n',
    )
    assert _codes(root) == [
        "ignore-comment/certain-finding",
        "ignore-comment/unclosed-block",
        "ignore-comment/unknown-check",
        "ignore-comment/unused",
        "reality/history-narration",
    ]


def test_comments_in_code_spans_are_not_markers(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Write `<!-- irminsul:ignore reality -->` on the line.\n")
    assert _codes(root) == []


def test_a_comment_without_a_reason_is_reported(tmp_path: Path) -> None:
    """A blanket block with no reason silenced whole checks and explained nothing."""
    root = _repo(
        tmp_path,
        "<!-- irminsul:ignore-start reality -->\nPreviously A.\n"
        "<!-- irminsul:ignore-end reality -->\n",
    )
    assert "ignore-comment/no-reason" in _codes(root)


def test_an_empty_reason_counts_as_none(tmp_path: Path) -> None:
    root = _repo(tmp_path, '<!-- irminsul:ignore reality reason="  " -->\nPreviously A.\n')
    assert "ignore-comment/no-reason" in _codes(root)


def test_a_comment_quoted_inside_a_nested_fence_suppresses_nothing(tmp_path: Path) -> None:
    """A four-backtick example quoting a three-backtick block is still one example, so the
    ignore comment inside it is text to read, not a suppression of the prose after it."""
    root = _repo(
        tmp_path,
        "````markdown\n"
        "```md\n"
        '<!-- irminsul:ignore reality reason="an example of the syntax" -->\n'
        "```\n"
        "````\n\n"
        "The store previously used SQLite.\n",
    )
    assert _codes(root) == ["reality/history-narration"]


def test_backticks_inside_a_tilde_fence_do_not_close_it() -> None:
    """Scanned at the unit level: other checks still toggle on any fence line, so the prose
    after this example is not reported to begin with, and nothing would show a suppression."""
    from irminsul.checks.ignore_comments import _scan

    lines = [
        "~~~",
        "```",
        '<!-- irminsul:ignore reality reason="an example of the syntax" -->',
        "~~~",
        "",
        "The store previously used SQLite.",
    ]
    comments: list = []
    problems: list = []
    _scan(Path("docs/a.md"), "a", list(enumerate(lines, 1)), comments, problems)

    assert comments == []
    assert problems == []
