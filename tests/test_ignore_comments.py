"""Ignore comments suppress soft-check findings on the lines they cover."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from .conftest import check_codes, check_findings, write_config

runner = CliRunner()

# Two hints on two distinct codes: a call no source defines, and a variable no source reads.
_UNKNOWN_CALL = "The store opens with `load_store()`."
_UNKNOWN_VAR = "It reads `STORE_PATH`."


def _repo(root: Path, body: str) -> Path:
    write_config(root, source_roots=["src"], enabled=["frontmatter", "code-references"])
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        'import os\n\nHOME = os.environ.get("APP_HOME")\n\n\ndef run():\n    return HOME\n',
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "store.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        f"---\nid: store\ntitle: Store\nstatus: stable\nsummary: A test doc.\n---\n\n# Store\n\n{body}",
        encoding="utf-8",
    )
    return root


def test_the_vehicle_reports_both_hints(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"{_UNKNOWN_CALL}\n\n{_UNKNOWN_VAR}\n")
    assert check_codes(root) == [
        "code-references/unknown-env-var",
        "code-references/unknown-symbol",
    ]


def test_a_comment_suppresses_its_own_line(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        f'{_UNKNOWN_CALL} <!-- irminsul:ignore code-references reason="quoted" -->\n'
        f"{_UNKNOWN_VAR}\n",
    )
    assert check_codes(root) == ["code-references/unknown-env-var"]


def test_a_standalone_comment_covers_the_next_line_and_codes_match(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        '<!-- irminsul:ignore code-references/unknown-symbol reason="quoted" -->\n\n'
        f"{_UNKNOWN_CALL}\n",
    )
    assert check_codes(root) == []


def test_a_block_covers_every_line_inside_it(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        '<!-- irminsul:ignore-start code-references reason="quoted" -->\n'
        f"{_UNKNOWN_CALL}\n\n{_UNKNOWN_VAR}\n"
        "<!-- irminsul:ignore-end code-references -->\nIt closes with `close_store()`.\n",
    )
    assert check_codes(root) == ["code-references/unknown-symbol"]


def test_misused_comments_are_reported(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        'Plain text. <!-- irminsul:ignore code-references reason="suppresses nothing" -->\n\n'
        f'{_UNKNOWN_CALL} <!-- irminsul:ignore links reason="certain code" -->\n\n'
        'Text. <!-- irminsul:ignore nonsense reason="unknown check" -->\n\n'
        '<!-- irminsul:ignore-start code-references reason="never closed" -->\n',
    )
    assert check_codes(root) == [
        "code-references/unknown-symbol",
        "ignore-comment/certain-finding",
        "ignore-comment/unclosed-block",
        "ignore-comment/unknown-check",
        "ignore-comment/unused",
    ]


def test_a_comment_for_a_code_its_check_no_longer_has_is_unknown(tmp_path: Path) -> None:
    """A tree written for an earlier version keeps comments for codes that were removed from
    checks that still exist; each is reported as naming nothing, not a crash of the run."""
    root = _repo(
        tmp_path,
        f'{_UNKNOWN_CALL} <!-- irminsul:ignore code-references/retired-code reason="old" -->\n',
    )
    assert check_codes(root) == [
        "code-references/unknown-symbol",
        "ignore-comment/unknown-check",
    ]


def test_comments_in_code_spans_are_not_markers(tmp_path: Path) -> None:
    root = _repo(tmp_path, "Write `<!-- irminsul:ignore code-references -->` on the line.\n")
    assert check_codes(root) == []


def test_a_comment_without_a_reason_is_reported(tmp_path: Path) -> None:
    """A blanket block with no reason silenced whole checks and explained nothing."""
    root = _repo(
        tmp_path,
        f"<!-- irminsul:ignore-start code-references -->\n{_UNKNOWN_CALL}\n"
        "<!-- irminsul:ignore-end code-references -->\n",
    )
    assert "ignore-comment/no-reason" in check_codes(root)


def test_an_empty_reason_counts_as_none(tmp_path: Path) -> None:
    root = _repo(
        tmp_path, f'<!-- irminsul:ignore code-references reason="  " -->\n{_UNKNOWN_CALL}\n'
    )
    assert "ignore-comment/no-reason" in check_codes(root)


def test_a_comment_quoted_inside_a_nested_fence_suppresses_nothing(tmp_path: Path) -> None:
    """A four-backtick example quoting a three-backtick block is still one example, so the
    ignore comment inside it is text to read, not a suppression of the prose after it."""
    root = _repo(
        tmp_path,
        "````markdown\n"
        "```md\n"
        '<!-- irminsul:ignore code-references reason="an example of the syntax" -->\n'
        "```\n"
        "````\n\n"
        f"{_UNKNOWN_CALL}\n",
    )
    assert check_codes(root) == ["code-references/unknown-symbol"]


def test_backticks_inside_a_tilde_fence_do_not_close_it() -> None:
    """Scanned at the unit level: other checks still toggle on any fence line, so the prose
    after this example is not reported to begin with, and nothing would show a suppression."""
    from irminsul.checks.ignore_comments import _scan

    lines = [
        "~~~",
        "```",
        '<!-- irminsul:ignore code-references reason="an example of the syntax" -->',
        "~~~",
        "",
        _UNKNOWN_CALL,
    ]
    comments: list = []
    problems: list = []
    _scan(Path("docs/a.md"), "a", list(enumerate(lines, 1)), comments, problems, set())

    assert comments == []
    assert problems == []


# A fenced block whose third line names a variable no source reads.
_FENCE = "```text\nexport it first\nSTORE_PATH\n```\n"
_ENV_COMMENT = (
    '<!-- irminsul:ignore code-references/unknown-env-var reason="the shell sets it" -->\n'
)


def test_a_fenced_variable_is_reported(tmp_path: Path) -> None:
    assert check_codes(_repo(tmp_path, _FENCE)) == ["code-references/unknown-env-var"]


def test_a_comment_above_a_fence_covers_its_lines(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"{_ENV_COMMENT}\n{_FENCE}")
    assert check_codes(root) == []


def test_a_comment_above_a_fence_covers_that_fence_and_not_the_line_after(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, f"{_ENV_COMMENT}{_FENCE}\n{_UNKNOWN_VAR}\n")
    reported = [(f["code"], f["line"]) for f in check_findings(root)]
    assert reported == [("code-references/unknown-env-var", 16)]


def test_a_block_around_a_fence_covers_its_lines(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        '<!-- irminsul:ignore-start code-references/unknown-env-var reason="the shell sets it" -->\n'
        f"{_FENCE}"
        "<!-- irminsul:ignore-end code-references/unknown-env-var -->\n",
    )
    assert check_codes(root) == []


def test_a_comment_inside_a_fence_covers_nothing_and_is_not_reported(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        "```md\n"
        '<!-- irminsul:ignore code-references reason="an example of the syntax" -->\n'
        "STORE_PATH\n"
        "```\n",
    )
    assert check_codes(root) == ["code-references/unknown-env-var"]


def test_the_waiving_comment_is_written_in_the_grammar_the_pass_reads() -> None:
    from irminsul.checks.ignore_comments import _COMMENT_RE, comment_for

    match = _COMMENT_RE.fullmatch(comment_for("code-references/unknown-path"))

    assert match is not None
    assert match["names"].split() == ["code-references/unknown-path"]
    assert match["kind"] is None
