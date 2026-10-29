---
id: a-baseline-holds-certain-findings-and-grows-only-by-decision
title: A baseline holds certain findings and grows only by decision
status: stable
describes: []
summary: The baseline records only certain findings a check reports, is created once, loses entries as they are fixed, gains them only in a change that adds a decision record naming it, and shows what it hides.
governs:
  - src/irminsul/baseline.py
  - src/irminsul/delta.py
  - src/irminsul/checks/diff_integrity.py#_baseline_ratchet
  - src/irminsul/checks/diff_integrity.py#_entries
  - src/irminsul/checks/pipeline.py#BaselineStatus
  - src/irminsul/checks/pipeline.py#without_baselined
  - src/irminsul/checks/pipeline.py#run_delta
  - src/irminsul/cli.py#_report_hidden_to_github
  - src/irminsul/cli.py#_run_without_baseline
  - src/irminsul/cli.py#baseline_init
  - src/irminsul/cli.py#baseline_update
  - src/irminsul/cli.py#list_baseline
  - paths.baseline
---

# A baseline holds certain findings and grows only by decision

## Status

Accepted, 2026-10-28.

## Context

A baseline lets a repository adopt Irminsul with findings it cannot fix on day one: old ones
stop failing CI, new ones still do. A command that rewrote it from whatever fired would let an
agent record a new error and pass, and one recorded hint with a generic message would hide
every later one like it. A strict ratchet fails the other way: an upgrade whose new rule finds
12 certain problems in old docs could not merge until all 12 were fixed in its pull request.

## Decision

- **Only certain findings a check reports are baselined.** Hints and time findings fail a run
  only when asked, so the baseline neither records nor hides them. A pass that judges something
  other than the tree, such as `diff-integrity`, `co-change` or `history-depth`, and a code
  that audits a suppression are never debt; `--delta` asks the same question.
- **`--delta` refuses what it cannot answer**, such as a configured tree in another repository,
  rather than reporting everything there as new.
- **An entry is the finding's check, path and message**, not its line, so a finding that only
  moves stays hidden. A certain message names its item, such as the broken link's target, so
  an entry does not hide a different problem in the same doc.
- **Created once, then shrunk.** `irminsul baseline init` records the whole run
  `checks.enabled` names, and refuses when a baseline exists. `irminsul baseline update`
  removes entries that no longer match; when a certain finding the file does not record is
  present it lists it, writes nothing and exits 1. No command adds an entry to an existing
  baseline.
- **Grows only by decision.** Under `--diff`, a baseline holding entries its merge base did not
  is `diff-integrity/baseline-grew`, certain, unless the change adds a stable decision record
  whose `## Decision` names the baseline file's path in a code span, or is the adopting change,
  whose base has neither an `irminsul.toml` nor a baseline. The record says why the findings
  wait, and the change deletes the file and runs `baseline init` again.
- **What it hides is visible.** A run that applies a baseline prints how many findings it hid
  and how many entries are fixed, and JSON always carries a `baseline` object.
  `--format github` adds a warning annotation and, when `GITHUB_STEP_SUMMARY` is set, lists
  every hidden finding there. `irminsul list baseline` lists each entry and whether it matches.
- **A narrowed run counts only what it could match:** `check --only <check>` does not count the
  entries of enabled checks it left out as fixed. `check --no-baseline` changes one run, writes
  nothing, and is exclusive with `--delta`.
- **No expiry.** An entry hides its finding until the finding is fixed or its message changes.
- **A trailer naming the baseline answers its growth** (accepted, not yet implemented), in
  place of a decision record the change adds; the adopting change stays exempt.

Files with no owning doc at adoption are excepted by the
[adoption record](../components/adoption-record.md) instead, whose files `uniqueness` skips.

## Alternatives Considered

- **Count matches per entry.** Rejected: fixing one finding and adding another keeps the count.
- **Identify an entry by line or paragraph text.** Rejected: rewrapping would revive old
  findings.
- **Expire entries.** Rejected: the failure lands on whoever opens the next pull request.
- **Strictly only shrinks, or growth only from newly enabled checks.** Rejected: an upgrade
  usually adds codes to checks already enabled, and could not merge.
- **A command that adds entries, or `--only` on the maintenance commands.** Rejected: delete
  and re-create already grows it, the seal is what the reviewer sees, and a partial `init`
  would record part of a run.

## Consequences

- An agent that hits a new certain finding has no command that records it, and a hand edit
  fails `diff-integrity`.
- An upgrade has a reviewed way through; the record proves a reason was written, not that
  anyone agreed.
- `baseline update` cannot be narrowed, so it removes the entries of a check taken out of
  `checks.enabled`.

## Changes

- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  a trailer naming the baseline answers its growth.
