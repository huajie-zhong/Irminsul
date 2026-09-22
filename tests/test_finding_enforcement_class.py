"""What a finding enforces as, and that every surface answers the same way.

The draft exemption demotes a certain finding to a warning. Before this was pinned, the
three surfaces disagreed about what that demoted finding then was: the JSON said
`certain`, the exit code treated it as a hint, and the ignore-comment rule kept treating
it as certain. Those tests fix the relationship rather than any one surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_ADR = """---
id: {slug}
title: "ADR: {slug}"
status: {status}
describes: []
---

# ADR: {slug}

## Context

Some situation prompted a decision.

## Decision

We will do the thing.
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(root: Path, status: str) -> Path:
    _write(
        root,
        "irminsul.toml",
        'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["app"]\n'
        '[checks]\nenabled = ["frontmatter", "adr-structure"]\n',
    )
    _write(root, "app/.gitkeep", "")
    _write(root, "docs/decisions/0001-bare.md", _ADR.format(slug="0001-bare", status=status))
    return root


def _findings(root: Path, *extra: str) -> tuple[int, list[dict[str, str]]]:
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root), *extra])
    payload = json.loads(result.output)
    return result.exit_code, [f for f in payload["findings"] if f["check"] == "adr-structure"]


def _exit(root: Path, *extra: str) -> int:
    return runner.invoke(app, ["check", "--path", str(root), *extra]).exit_code


def test_a_demoted_finding_reports_both_classes(tmp_path: Path) -> None:
    """`class` stays the code's own, so `explain` and the ignore rule still recognise it;
    `effective_class` is what this occurrence enforces as."""
    root = _repo(tmp_path, "draft")

    _, findings = _findings(root)

    assert findings
    for finding in findings:
        assert finding["code"] == "adr-structure/missing-section"
        assert finding["class"] == "certain"
        assert finding["effective_class"] == "hint"
        assert finding["severity"] == "warning"


def test_a_stable_doc_reports_one_class_twice(tmp_path: Path) -> None:
    root = _repo(tmp_path, "stable")

    _, findings = _findings(root)

    assert findings
    for finding in findings:
        assert finding["class"] == "certain"
        assert finding["effective_class"] == "certain"
        assert finding["severity"] == "error"


def test_the_effective_class_predicts_the_exit_code_on_a_draft(tmp_path: Path) -> None:
    root = _repo(tmp_path, "draft")

    assert _exit(root) == 0
    assert _exit(root, "--fail-on", "certain") == 0
    assert _exit(root, "--fail-on", "hint") == 1
    assert _exit(root, "--strict") == 1


def test_the_effective_class_predicts_the_exit_code_on_a_stable_doc(tmp_path: Path) -> None:
    root = _repo(tmp_path, "stable")

    assert _exit(root) == 1
    assert _exit(root, "--fail-on", "certain") == 1
    assert _exit(root, "--fail-on", "hint") == 1
    assert _exit(root, "--strict") == 1


def test_severity_is_the_effective_class_in_the_older_vocabulary(tmp_path: Path) -> None:
    """The two must not drift: an error is exactly an effectively-certain finding."""
    for status in ("draft", "stable"):
        root = _repo(tmp_path / status, status)
        _, findings = _findings(root)
        assert findings
        for finding in findings:
            errored = finding["severity"] == "error"
            assert errored == (finding["effective_class"] == "certain")


def test_a_demoted_finding_is_still_not_silenceable(tmp_path: Path) -> None:
    """Suppression reads the declared class, because a comment names a code and cannot
    depend on the status of the doc it happens to land in. Demotion is not a way in."""
    root = _repo(tmp_path, "draft")
    doc = root / "docs" / "decisions" / "0001-bare.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "# ADR: 0001-bare",
            "# ADR: 0001-bare\n\n<!-- irminsul:ignore adr-structure/missing-section "
            'reason="it is only a draft" -->',
        ),
        encoding="utf-8",
    )

    _, findings = _findings(root)

    assert [f["code"] for f in findings] == ["adr-structure/missing-section"] * 3
