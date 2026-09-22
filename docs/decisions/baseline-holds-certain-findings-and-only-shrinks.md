---
id: baseline-holds-certain-findings-and-only-shrinks
title: Baseline holds certain findings and only shrinks
status: stable
describes: []
summary: The baseline records only certain findings, is created once and afterwards only loses entries, and every run shows people what it hides.
---

# Baseline holds certain findings and only shrinks

## Status

Accepted, 2026-09-15.

## Context

A baseline exists so a repository can adopt Irminsul with findings it cannot fix on day
one: old findings stop failing CI, new ones still do. Two things let it bury problems
instead.

`check --update-baseline` rewrote the whole file from whatever fired, so an agent that hit
a new error could record it and pass. `diff-integrity` catches a baseline that grew in a
pull request, but not a rewrite pushed directly or run locally.

A baseline entry is the check, path, and message of a finding, and before
[Finding classes decide what blocks](finding-classes-decide-what-blocks.md) the file also recorded hints. A hint's
message is often generic: one baselined `speculative keyword 'planned'` in a doc hid every
later "planned" in that doc. Hints do not block, so recording them hid them for nothing.

## Decision

- **Only certain findings are baselined.** Hint and time findings do not fail the run a
  repository adopts with — `--strict` and `--fail-on` still reach them, so "never fail a
  run" was too strong — and a baseline exists to stop day-one findings failing CI, so it
  neither records nor hides them. A certain finding's message names the item
  it is about, such as the broken link's target, so an entry does not hide a different
  problem in the same doc.
- **Created once.** `check --init-baseline` writes the file from the current certain
  findings and refuses when a baseline already exists.
- **Only shrinks afterwards.** `check --update-baseline` removes entries that no longer
  match and refuses, listing them, when a certain finding the file does not record is
  present. No command adds an entry to an existing baseline.
- **What it hides is visible.** Every run reports how many findings the baseline hid and
  how many entries are fixed. `--format github` adds a warning annotation, and when
  `GITHUB_STEP_SUMMARY` is set it lists every hidden finding in the job summary.
  `irminsul list baseline` lists every entry and whether it still matches.
- **No expiry.** An entry keeps hiding its finding until the finding is fixed or its
  message changes. A date-based expiry would fail an unrelated pull request on the day
  the entry ran out.

## Alternatives Considered

- **Count matches per entry.** Rejected: fixing one finding and adding another keeps the
  count, so the swap stays hidden, and a count says nothing about which finding is old.
- **Identify an entry by its line, or by its paragraph's text.** Rejected: rewrapping
  prose would make old findings reappear, and once hints leave the baseline the certain
  messages already name their item.
- **Expire entries after a number of days.** Rejected: the failure lands on whoever opens
  the next pull request, not on whoever owns the debt.

## Consequences

- An agent that hits a new certain finding has no command that records it; it fixes the
  finding, and a pull request that edits the file by hand fails `diff-integrity`.
- A repository adopting an upgrade that turns warnings into certain findings runs
  `check --init-baseline` after deleting its old baseline, once.
- Reviewers see the hidden debt in CI without opening the file.
