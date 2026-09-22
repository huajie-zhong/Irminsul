"""Unit tests for the baseline (ratchet) module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irminsul.baseline import (
    BaselineError,
    apply_baseline,
    baselinable,
    fingerprint,
    init_baseline,
    load_baseline,
    shrink_baseline,
)
from irminsul.checks.base import Finding, Severity


def _finding(
    check: str = "frontmatter",
    severity: Severity = Severity.error,
    message: str = "missing required field 'audience'",
    path: str | None = "docs/components/a.md",
    line: int | None = 3,
    code: str = "frontmatter/parse-error",
) -> Finding:
    return Finding(
        check=check,
        code=code,
        severity=severity,
        message=message,
        path=Path(path) if path is not None else None,
        line=line,
    )


def _hint(message: str = "speculative keyword 'planned'") -> Finding:
    return _finding(
        check="reality",
        severity=Severity.warning,
        message=message,
        code="reality/speculative-language",
    )


def test_fingerprint_ignores_line_and_severity() -> None:
    moved = _finding(line=42)
    promoted = _finding(severity=Severity.warning)
    base = _finding()
    fps = {
        fingerprint(f.check, f.path.as_posix() if f.path else "", f.message)
        for f in (base, moved, promoted)
    }
    assert len(fps) == 1


def test_fingerprint_changes_with_message() -> None:
    a = fingerprint("frontmatter", "docs/a.md", "missing 'audience'")
    b = fingerprint("frontmatter", "docs/a.md", "missing 'status'")
    assert a != b


def test_init_records_only_certain_findings_once(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    findings = [_finding(), _finding(line=99), _hint()]
    assert init_baseline(target, findings) == 1
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert [entry["check"] for entry in payload["findings"]] == ["frontmatter"]


def test_init_refuses_an_existing_baseline(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    init_baseline(target, [_finding()])
    with pytest.raises(BaselineError, match="already exists"):
        init_baseline(target, [_finding()])


def test_init_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "ci" / "nested" / "baseline.json"
    assert init_baseline(target, [_finding()]) == 1
    assert target.is_file()


def test_shrink_removes_fixed_entries(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    kept = _finding()
    init_baseline(target, [kept, _finding(message="fixed since")])
    result = shrink_baseline(target, [kept, _hint()])
    assert (result.new, result.removed, result.kept) == ([], 1, 1)
    assert load_baseline(target) == {
        fingerprint("frontmatter", "docs/components/a.md", kept.message)
    }


def test_shrink_refuses_a_new_certain_finding_and_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    init_baseline(target, [_finding()])
    before = target.read_text(encoding="utf-8")
    new = _finding(message="a brand new violation")
    result = shrink_baseline(target, [_finding(), new, _hint()])
    assert result.new == [new]
    assert target.read_text(encoding="utf-8") == before


def test_shrink_needs_an_existing_baseline(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="--init-baseline"):
        shrink_baseline(tmp_path / "baseline.json", [_finding()])


def test_load_recomputes_fingerprint_from_fields(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    init_baseline(target, [_finding()])
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["findings"][0]["fingerprint"] = "tampered"
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert load_baseline(target) == {
        fingerprint("frontmatter", "docs/components/a.md", _finding().message)
    }


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"version": 99, "findings": []}',
        '{"version": 1}',
        '{"version": 1, "findings": [{"check": "frontmatter"}]}',
    ],
)
def test_load_rejects_malformed_baseline(tmp_path: Path, content: str) -> None:
    target = tmp_path / "baseline.json"
    target.write_text(content, encoding="utf-8")
    with pytest.raises(BaselineError):
        load_baseline(target)


def test_apply_hides_only_certain_findings_and_counts_stale(tmp_path: Path) -> None:
    baselined = _finding()
    target = tmp_path / "baseline.json"
    init_baseline(target, [baselined, _finding(message="fixed since")])
    fps = load_baseline(target)
    fps.add(fingerprint("reality", "docs/components/a.md", _hint().message))

    new = _finding(message="a brand new violation")
    hint = _hint()
    result = apply_baseline([baselined, new, hint], fps)

    assert result.remaining == [new, hint]
    assert result.hidden == [baselined]
    assert result.stale == 2


def test_apply_hides_line_moves(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    init_baseline(target, [_finding(line=3)])
    result = apply_baseline([_finding(line=77)], load_baseline(target))
    assert result.remaining == []
    assert result.suppressed == 1
    assert result.stale == 0


def test_load_treats_null_path_as_empty_string(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    target.write_text(
        json.dumps(
            {
                "version": 1,
                "findings": [{"check": "globs", "path": None, "message": "repo-wide problem"}],
            }
        ),
        encoding="utf-8",
    )
    assert load_baseline(target) == {fingerprint("globs", "", "repo-wide problem")}


def test_no_suppression_audit_is_baselinable() -> None:
    """`baselinable` promises "a baseline cannot hide an obsolete exception", but the
    exclusion was a hand-written code list in this module, and only one of the three
    suppression-audit codes was on it.

    An unclosed `ignore-start` silences the rest of a doc, so baselining it buries the
    broken marker and everything it goes on to swallow.
    """
    from irminsul.checks.pipeline import audits_suppression

    assert audits_suppression(), "no check declares a suppression-audit code"
    for code in sorted(audits_suppression()):
        check, _, category = code.partition("/")
        finding = Finding(
            check=check,
            code=code,
            category=category,
            severity=Severity.error,
            message="m",
            path=Path("docs/components/d.md"),
        )
        assert not baselinable(finding), f"{code} can be hidden by a baseline"
