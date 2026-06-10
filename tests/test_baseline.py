"""Unit tests for the baseline (ratchet) module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irminsul.baseline import (
    BaselineError,
    apply_baseline,
    fingerprint,
    load_baseline,
    write_baseline,
)
from irminsul.checks.base import Finding, Severity


def _finding(
    check: str = "frontmatter",
    severity: Severity = Severity.error,
    message: str = "missing required field 'audience'",
    path: str | None = "docs/20-components/a.md",
    line: int | None = 3,
) -> Finding:
    return Finding(
        check=check,
        severity=severity,
        message=message,
        path=Path(path) if path is not None else None,
        line=line,
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
    b = fingerprint("frontmatter", "docs/a.md", "missing 'tier'")
    assert a != b


def test_write_baseline_excludes_info_and_dedupes(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    findings = [
        _finding(),
        _finding(line=99),  # same identity, different line — one entry
        _finding(check="orphans", severity=Severity.warning, message="no inbound refs"),
        _finding(check="claim-anchor", severity=Severity.info, message="anchor not pinned"),
    ]
    count = write_baseline(target, findings)
    assert count == 2
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    checks = [entry["check"] for entry in payload["findings"]]
    assert checks == sorted(checks)
    assert "claim-anchor" not in checks


def test_write_then_load_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    write_baseline(target, [_finding()])
    fps = load_baseline(target)
    assert fps == {fingerprint("frontmatter", "docs/20-components/a.md", _finding().message)}


def test_load_recomputes_fingerprint_from_fields(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    write_baseline(target, [_finding()])
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["findings"][0]["fingerprint"] = "tampered"
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert load_baseline(target) == {
        fingerprint("frontmatter", "docs/20-components/a.md", _finding().message)
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


def test_apply_baseline_partitions_and_counts_stale(tmp_path: Path) -> None:
    baselined = _finding()
    target = tmp_path / "baseline.json"
    write_baseline(target, [baselined, _finding(check="gone", message="fixed since")])
    fps = load_baseline(target)

    new = _finding(message="a brand new violation")
    info = _finding(check="claim-anchor", severity=Severity.info, message="anchor not pinned")
    result = apply_baseline([baselined, new, info], fps)

    assert result.remaining == [new, info]
    assert result.suppressed == 1
    assert result.stale == 1


def test_apply_baseline_suppresses_line_moves(tmp_path: Path) -> None:
    target = tmp_path / "baseline.json"
    write_baseline(target, [_finding(line=3)])
    result = apply_baseline([_finding(line=77)], load_baseline(target))
    assert result.remaining == []
    assert result.suppressed == 1
    assert result.stale == 0
