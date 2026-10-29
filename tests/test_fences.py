"""Tests for the one fenced-code-block reader every consumer shares."""

from __future__ import annotations

from pathlib import Path

from irminsul.anchors import parse_anchors
from irminsul.fences import FenceTracker

SRC = Path(__file__).resolve().parent.parent / "src" / "irminsul"


def _kinds(body: str) -> list[str]:
    fence = FenceTracker()
    return [fence.classify(line) for line in body.splitlines()]


def test_a_longer_fence_quotes_a_shorter_one_verbatim() -> None:
    body = "prose\n````markdown\n```\ninner\n```\n````\nafter"
    assert _kinds(body) == [
        "outside",
        "marker",
        "content",
        "content",
        "content",
        "marker",
        "outside",
    ]


def test_a_backtick_run_inside_a_tilde_block_is_content() -> None:
    body = "~~~\n```\nstill inside\n~~~\nafter"
    assert _kinds(body) == ["marker", "content", "content", "marker", "outside"]


def test_a_closing_marker_may_not_carry_an_info_string() -> None:
    body = "```\nbody\n``` trailing\n```\nafter"
    assert _kinds(body) == ["marker", "content", "content", "marker", "outside"]


def test_the_open_block_reports_its_language_label() -> None:
    fence = FenceTracker()
    assert fence.info == ""
    assert fence.classify("```python") == "marker"
    assert fence.info == "python"
    assert fence.classify("x = 1") == "content"
    assert fence.info == "python"
    assert fence.classify("```") == "marker"
    assert fence.info == ""


def test_an_anchor_quoted_in_a_longer_fence_is_not_read() -> None:
    """The defect this reader exists to stop.

    Documenting the anchor syntax needs a four-backtick fence around a three-backtick
    example. Read with a naive toggle, the inner marker closed the block and the example
    became a live anchor — a certain finding on a document that was correct, and one no
    ignore comment could silence.
    """
    body = (
        "How an anchor looks:\n\n"
        "````markdown\n"
        "```\n"
        "<!-- anchor: src/nowhere.py#run @sha256:deadbeefcafe -->\n"
        "```\n"
        "````\n\n"
        "And a live one:\n\n"
        "<!-- anchor: src/real.py#run -->\n"
    )
    assert [anchor.path for anchor in parse_anchors(body)] == ["src/real.py"]


def test_only_the_fences_module_reads_a_fence_itself() -> None:
    """A second local reading is the defect itself, so this fails when one reappears.

    The inputs are asserted before the conclusion: a scan that silently matched nothing
    would report success for ever while reading no files at all.
    """
    scanned = sorted(SRC.rglob("*.py"))
    assert "fences.py" in {path.name for path in scanned}, "the scan found no fences module"
    assert len(scanned) > 50, f"only {len(scanned)} files scanned, so the scan is not working"

    offenders: dict[str, list[str]] = {}
    for path in scanned:
        if path.name == "fences.py":
            continue
        reasons = []
        body = path.read_text(encoding="utf-8")
        if "in_fence" in body:
            reasons.append("tracks fenced-block state in a local variable")
        reasons += [
            f"compiles its own fence pattern: {line.strip()}"
            for line in body.splitlines()
            if "re.compile" in line and ("```" in line or "~~~" in line)
        ]
        if reasons:
            offenders[path.relative_to(SRC).as_posix()] = reasons
    assert offenders == {}, f"fence reading outside irminsul.fences: {offenders}"
