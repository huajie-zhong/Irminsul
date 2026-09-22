---
id: switching-a-check-off-is-more-than-a-list-edit
title: Switching a check off is more than a list edit
status: stable
describes: []
summary: The config seal covers the settings that decide how much a check asks, not only the list of checks, and a CI step counts as a gate only if its result can fail the run.
---

# Switching a check off is more than a list edit

## Status

Accepted, 2026-09-19.

## Context

[Weakening the config needs a decision record](weakening-the-config-needs-a-decision-record.md)
sealed `checks.enabled`, the layer rules, and what the source walk reads. Reviewing the
seal against the schema found the same effect reachable without touching any of them.

`external-links` has its own `enabled` key. Setting it to `false` leaves the name in
`checks.enabled`, so the sealed list is untouched and the check stops running.
`mtime_drift_days` widened from 30 to 3650 leaves every check enabled and stops one of
them firing; `deprecated_threshold_days`, `accepted_threshold_days` and
`length_warning_lines` are the same shape, and `glossary_path` repointed at an empty file
silences a check without editing it. Each passed `check --diff` at exit 0.

The CI side had the mirror of it. Gate strength was counted from the flags on lines
naming `irminsul check`, so a step keeping every flag while discarding its result scored
full strength: `continue-on-error: true`, `if: false`, and `irminsul check … || true` all
passed unreported.

## Decision

- **A setting that decides how much a check asks is sealed like the check itself**
  (`diff-integrity/setting-weakened`, certain): a per-check `enabled` turned off, a
  threshold widened so the check fires on less, or the glossary repointed. The same
  decision record clears it, naming the setting in a code span.
- **A rule removed from a configured list is a hint** (`diff-integrity/source-excluded`),
  compared by the identity of what it watched — a term, a `(kind, glob)` pair, a framework
  pack — because a shorter list and an edited rule look alike by length alone.
- **A settings table that changed with no rule to judge it is a hint**
  (`diff-integrity/unreviewed-setting-change`). The comparison above is a hand-written
  list and nothing mechanical notices what is missing from it, so the next setting added
  to the schema would otherwise be a free bypass until somebody remembered to seal it.
- **A CI step counts as a gate only if its result can fail the run.** A step or job with
  `continue-on-error: true`, an `if:` that is statically false, or a command ending
  `|| true` (or a block that sets `+e` or ends `exit 0`) contributes nothing to gate
  strength, so removing the gate and neutering it read the same.
- **Only a provably false condition disables a step.** `if: github.event_name ==
  'pull_request'` is an ordinary conditional gate; evaluating it needs the event.

## Alternatives Considered

- **Comparing the config as text.** Rejected: a reformat would report, and a semantically
  equivalent rewrite would not be recognised as equivalent.
- **Treating every non-static `if:` as disabling.** Rejected: it would report the
  conditional step this repository's own workflow uses, and every matrix workflow like it.
- **Reading the shell.** Rejected for anything past the three spellings above. A general
  reading of control flow is not something a regex does, and guessing reports working
  scripts.
- **Ranking `uses:` versions to catch a downgrade.** Rejected: refs are tags, branches and
  shas with no total order, so `@v1 → @<sha>` — an ordinary pin — is indistinguishable
  from a downgrade.

## Consequences

- Widening a threshold now needs a decision record, which is the intended friction and
  will be felt by anyone adopting Irminsul on an old tree.
- **The record proves a reason was written down, not that anyone agreed to it.** The same
  author, in the same commit, can weaken a setting and add the record that clears it, and
  the run goes green — measured, not assumed. What the seal removes is silence: the
  weakening cannot land unremarked, and the reason is in the decisions layer where the
  reviewer and every later change inherit it. Whether the reason is good, and whether the
  person writing it may decide such things, is a question about people and permissions.
  Nothing in this repository can answer it: a check reads the tree it is given, and the
  tree cannot tell it who approved what. Requiring a second pair of eyes is branch
  protection and review settings on the forge — see
  [enforcement](../foundation/enforcement.md) — and those are outside what any check here
  verifies.
- The unreviewed-setting hint fires on config changes nobody has classified. That is the
  point, and it is a hint: it asks, and does not block.
- A workflow that legitimately ends a `run:` block with `exit 0` after a gate reads as
  neutralised. Splitting the gate into its own step is the fix, and is clearer anyway.
