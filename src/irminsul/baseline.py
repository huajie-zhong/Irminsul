"""Baseline (ratchet) support for adopting Irminsul on an existing codebase.

A baseline file records the error and warning findings that existed when the
tool was adopted. When the file is present, `check` suppresses exactly those
findings and fails only on new ones, so a brownfield repo gets a green CI
immediately without grandfathering future regressions. The file only shrinks:
`--update-baseline` rewrites it from the current findings, and stale entries
(ones that no longer match anything) are surfaced so the ratchet visibly
tightens over time.

Matching is by fingerprint of ``(check, path, message)`` — deliberately
excluding the line number and severity, so a finding that merely moves within
a file stays suppressed, while one whose message changes counts as new.
Entries are stored human-readable and sorted, so the file diffs cleanly in
review; the stored fingerprint is a convenience and is recomputed on load.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from irminsul.checks.base import Finding, Severity

BASELINE_VERSION = 1


class BaselineError(Exception):
    """Raised when a baseline file exists but cannot be used."""


def fingerprint(check: str, path: str, message: str) -> str:
    """Stable identity of one finding: sha256 over check, path, and message."""
    return hashlib.sha256(f"{check}|{path}|{message}".encode()).hexdigest()


def finding_fingerprint(finding: Finding) -> str:
    """Fingerprint of a `Finding` — the same identity `fingerprint()` computes
    from raw fields, shared with `irminsul.delta` so a "new" finding means the
    same thing under `--delta` as it does under the baseline ratchet."""
    path = finding.path.as_posix() if finding.path is not None else ""
    return fingerprint(finding.check, path, finding.message)


@dataclass(frozen=True)
class BaselineApplication:
    """Outcome of filtering one check run through a baseline."""

    remaining: list[Finding]
    suppressed: int
    stale: int


def write_baseline(path: Path, findings: list[Finding]) -> int:
    """Write the baseline file from the current error/warning findings.

    Info findings are never baselined: they do not affect exit codes, so
    recording them would only bloat the file. Returns the entry count.
    """
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        if finding.severity is Severity.info:
            continue
        finding_path = finding.path.as_posix() if finding.path is not None else ""
        seen.add((finding.check, finding_path, finding.message))

    entries = [
        {
            "check": check,
            "path": finding_path,
            "message": message,
            "fingerprint": fingerprint(check, finding_path, message),
        }
        for check, finding_path, message in sorted(seen)
    ]
    payload = {"version": BASELINE_VERSION, "findings": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return len(entries)


def load_baseline(path: Path) -> set[str]:
    """Load a baseline file and return the set of finding fingerprints.

    Fingerprints are recomputed from the stored fields rather than trusted,
    so a hand-edited entry stays consistent with what `check` will match.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise BaselineError(f"could not read baseline {path.name}: {e}") from e

    if not isinstance(payload, dict) or payload.get("version") != BASELINE_VERSION:
        raise BaselineError(
            f"baseline {path.name} has unsupported format; "
            f"expected version {BASELINE_VERSION} — regenerate with --update-baseline"
        )
    raw_entries = payload.get("findings")
    if not isinstance(raw_entries, list):
        raise BaselineError(
            f"baseline {path.name} is missing its findings list — regenerate with --update-baseline"
        )

    fingerprints: set[str] = set()
    for entry in raw_entries:
        if not isinstance(entry, dict):
            raise BaselineError(f"baseline {path.name} contains a malformed entry")
        try:
            check = entry["check"]
            finding_path = entry["path"]
            message = entry["message"]
        except KeyError as e:
            raise BaselineError(
                f"baseline {path.name} entry is missing the {e.args[0]!r} field"
            ) from e
        # A null path in hand-edited JSON must hash like the empty string the
        # writer uses for pathless findings, not like the string "None".
        fingerprints.add(
            fingerprint(
                str(check) if check is not None else "",
                str(finding_path) if finding_path is not None else "",
                str(message) if message is not None else "",
            )
        )
    return fingerprints


def apply_baseline(findings: list[Finding], fingerprints: set[str]) -> BaselineApplication:
    """Split findings into suppressed (baselined) and remaining (new).

    Info findings always pass through. Stale counts baseline entries that
    matched nothing in this run — the ratchet headroom.
    """
    remaining: list[Finding] = []
    suppressed = 0
    matched: set[str] = set()
    for finding in findings:
        if finding.severity is Severity.info:
            remaining.append(finding)
            continue
        fp = finding_fingerprint(finding)
        if fp in fingerprints:
            suppressed += 1
            matched.add(fp)
        else:
            remaining.append(finding)
    return BaselineApplication(
        remaining=remaining,
        suppressed=suppressed,
        stale=len(fingerprints - matched),
    )
