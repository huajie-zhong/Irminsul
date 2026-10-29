"""Baseline (ratchet) support for adopting Irminsul on an existing codebase.

A baseline file records the certain findings that existed when the tool was adopted.
When the file is present, `check` hides exactly those findings and fails only on new
ones, so a brownfield repo gets a green CI immediately without grandfathering future
regressions. Hint and time findings fail a run only under `--fail-on`, so they are neither
recorded nor hidden.

The file is created once and then only shrinks: `init_baseline` refuses when a baseline
exists, and `shrink_baseline` removes entries that match nothing but refuses to record a
certain finding the file does not already hold.

Matching is by fingerprint of ``(check, path, message)`` — deliberately excluding the
line number and severity, so a finding that merely moves within a file stays hidden,
while one whose message changes counts as new. Entries are stored human-readable and
sorted, so the file diffs cleanly in review; the stored fingerprint is a convenience and
is recomputed on load.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from irminsul.atomic import write_atomic
from irminsul.checks.base import Finding
from irminsul.errors import UserError

BASELINE_VERSION = 1


class BaselineError(UserError):
    """Raised when a baseline file exists but cannot be used, or cannot be written."""


@dataclass(frozen=True)
class BaselineEntry:
    check: str
    path: str
    message: str

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.check, self.path, self.message)


@dataclass(frozen=True)
class BaselineApplication:
    """Outcome of filtering one check run through a baseline."""

    remaining: list[Finding]
    hidden: list[Finding]
    stale: int

    @property
    def suppressed(self) -> int:
        return len(self.hidden)


@dataclass(frozen=True)
class ShrinkResult:
    """Outcome of `shrink_baseline`: nothing is written while `new` is non-empty."""

    new: list[Finding] = field(default_factory=list)
    removed: int = 0
    kept: int = 0


def fingerprint(check: str, path: str, message: str) -> str:
    """Stable identity of one finding: sha256 over check, path, and message."""
    return hashlib.sha256(f"{check}|{path}|{message}".encode()).hexdigest()


def finding_fingerprint(finding: Finding) -> str:
    """Fingerprint of a `Finding` — the same identity `fingerprint()` computes
    from raw fields, shared with `irminsul.delta` so a "new" finding means the
    same thing under `--delta` as it does under the baseline ratchet."""
    path = finding.path.as_posix() if finding.path is not None else ""
    return fingerprint(finding.check, path, finding.message)


def may_be_debt(finding: Finding) -> bool:
    """Whether this finding can be existing debt at all: one a registered check reports
    that does not audit a suppression.

    The one rule for what may be carried rather than fixed, asked by the baseline and by
    `--delta` alike, so neither treats as debt what the other would not. A registered check
    judges the tree, and a tree can carry yesterday's problems. Every pass outside the
    registry judges something else — the change, the run's own ignore comments, the
    checkout, the adoption record — and so does a suppression audit; carrying one would
    hide a baseline's own growth, an obsolete exception, or a clone too shallow for the
    checks that read history.
    """
    from irminsul.checks import REGISTRY
    from irminsul.checks.pipeline import audits_suppression

    return finding.check in REGISTRY and finding.code not in audits_suppression()


def baselinable(finding: Finding) -> bool:
    """Whether the baseline records and hides this finding: a certain finding that may be
    debt. Hint and time findings fail a run only when asked, so the baseline neither
    records nor hides them."""
    from irminsul.checks.base import FindingClass
    from irminsul.checks.pipeline import class_of

    return class_of(finding.code) is FindingClass.certain and may_be_debt(finding)


def init_baseline(path: Path, findings: list[Finding]) -> int:
    """Create the baseline from the current certain findings. Returns the entry count."""
    if path.exists():
        raise BaselineError(
            f"baseline {path.name} already exists; run irminsul baseline update to remove fixed "
            "entries, since a baseline only shrinks",
            code=1,
        )
    entries = {_entry(finding) for finding in findings if baselinable(finding)}
    _write(path, entries)
    return len(entries)


def shrink_baseline(path: Path, findings: list[Finding]) -> ShrinkResult:
    """Drop the entries that match no current finding, and refuse to add any."""
    if not path.is_file():
        raise BaselineError(f"no baseline at {path.name}; create one with irminsul baseline init")
    recorded = load_entries(path)
    fingerprints = {entry.fingerprint for entry in recorded}
    current = [finding for finding in findings if baselinable(finding)]
    new = [finding for finding in current if finding_fingerprint(finding) not in fingerprints]
    if new:
        return ShrinkResult(new=new)
    live = {finding_fingerprint(finding) for finding in current}
    kept = {entry for entry in recorded if entry.fingerprint in live}
    _write(path, kept)
    return ShrinkResult(removed=len(set(recorded)) - len(kept), kept=len(kept))


def load_entries(path: Path) -> list[BaselineEntry]:
    """A baseline file's entries; `BaselineError` when it cannot be read or is not a version-1
    baseline."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise BaselineError(f"could not read baseline {path.name}: {e}") from e

    if not isinstance(payload, dict) or payload.get("version") != BASELINE_VERSION:
        raise BaselineError(
            f"baseline {path.name} has unsupported format; expected version "
            f"{BASELINE_VERSION} — delete it and run irminsul baseline init"
        )
    raw_entries = payload.get("findings")
    if not isinstance(raw_entries, list):
        raise BaselineError(
            f"baseline {path.name} is missing its findings list — delete it and run irminsul baseline init"
        )

    entries: list[BaselineEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise BaselineError(f"baseline {path.name} contains a malformed entry")
        try:
            check = raw["check"]
            finding_path = raw["path"]
            message = raw["message"]
        except KeyError as e:
            raise BaselineError(
                f"baseline {path.name} entry is missing the {e.args[0]!r} field"
            ) from e
        # A null path in hand-edited JSON must hash like the empty string the
        # writer uses for pathless findings, not like the string "None".
        entries.append(
            BaselineEntry(
                str(check) if check is not None else "",
                str(finding_path) if finding_path is not None else "",
                str(message) if message is not None else "",
            )
        )
    return entries


def load_baseline(path: Path) -> set[str]:
    """Load a baseline file and return the set of finding fingerprints.

    Fingerprints are recomputed from the stored fields rather than trusted,
    so a hand-edited entry stays consistent with what `check` will match.
    """
    return {entry.fingerprint for entry in load_entries(path)}


def apply_baseline(findings: list[Finding], fingerprints: set[str]) -> BaselineApplication:
    """Split findings into hidden (baselined) and remaining.

    Only certain findings can be hidden. Stale counts baseline entries that matched
    nothing in this run — the fixed entries `irminsul baseline update` removes.
    """
    remaining: list[Finding] = []
    hidden: list[Finding] = []
    matched: set[str] = set()
    for finding in findings:
        fp = finding_fingerprint(finding)
        if baselinable(finding) and fp in fingerprints:
            hidden.append(finding)
            matched.add(fp)
        else:
            remaining.append(finding)
    return BaselineApplication(
        remaining=remaining, hidden=hidden, stale=len(fingerprints - matched)
    )


def _entry(finding: Finding) -> BaselineEntry:
    path = finding.path.as_posix() if finding.path is not None else ""
    return BaselineEntry(finding.check, path, finding.message)


def _write(path: Path, entries: set[BaselineEntry]) -> None:
    payload = {
        "version": BASELINE_VERSION,
        "findings": [
            {
                "check": entry.check,
                "path": entry.path,
                "message": entry.message,
                "fingerprint": entry.fingerprint,
            }
            for entry in sorted(entries, key=lambda e: (e.check, e.path, e.message))
        ],
    }
    write_atomic(path, json.dumps(payload, indent=2) + "\n", newline="\n")
