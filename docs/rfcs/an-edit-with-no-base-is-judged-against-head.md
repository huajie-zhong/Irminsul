---
id: an-edit-with-no-base-is-judged-against-head
title: "An edit with no base is judged against HEAD"
status: stable
describes: []
rfc_state: accepted
affects:
  - context
resolved_by: docs/decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md
summary: "`context --after-edit` with no base judges the uncommitted work as the change, against HEAD, so the checks that judge a change speak before the first commit instead of at the pull request."
required_updates: []
weight: small
---

# An edit with no base is judged against HEAD

## Summary

When an agent checks its edits before committing and gives no base, the uncommitted work is
judged as the change, against the last commit. Today nothing is judged as a change then, so
two agents in the 2026-10-29 dogfood learned only at the pull request that editing a file the
adoption record lists needs a new doc. One decision, answered.

## Decisions

Answered by the owner on 2026-10-29:

1. **Judge uncommitted work against HEAD by default**, rather than keeping the run quiet until
   a base is given and only saying so.

## Design detail

- **Today.** `context --after-edit` runs the change checks (`co-change`, `diff-integrity`,
  `new-dependency`) only once `--base-ref`, `IRMINSUL_BASE_REF` or `GITHUB_BASE_REF` resolves;
  with none it prints a note, added on 2026-10-29, that they did not run.
- **The rule.** With no base and uncommitted work, the base is `HEAD`, which is the range
  `check --diff HEAD` already judges: "`--diff HEAD` is the uncommitted work" in
  `a-change-is-judged-from-its-merge-base-to-the-working-tree`. With `--committed-only` and no
  base, nothing is judged, as that record says. A clean tree with no base judges nothing.
- **The note.** The no-base note goes; the run names its base instead, as `list review
  --changed` does.
- **Evidence.** In the dogfood repo, an uncommitted edit to a recorded-debt file passed
  `context --after-edit` and failed `check --diff HEAD` with
  `diff-integrity/adoption-debt-touched`.
- **Governing record.** `a-change-is-judged-from-its-merge-base-to-the-working-tree`.

## Requirements

### Requirement: Uncommitted work is judged against HEAD
ID: uncommitted-work-is-judged-against-head
Provenance: code

`context --after-edit` with no base given and uncommitted work in the tree SHALL judge that
work as the change, with `HEAD` as its base, running the checks that judge a change.

#### Scenario: An edit to a recorded-debt file
- **WHEN** a file the adoption record lists is edited and not committed, and `context --after-edit` runs with no base
- **THEN** its change validation reports `diff-integrity/adoption-debt-touched`

#### Scenario: Committed only
- **WHEN** `context --after-edit --committed-only` runs with no base
- **THEN** nothing is judged as a change, and the run says so

## Tasks

- `T1` Default the after-edit base to `HEAD` when none is given and the tree is dirty. (req: uncommitted-work-is-judged-against-head)
- `T2` Name the base in the output and drop the no-base note. (component: context)

## Resolution

Accepted by the owner on 2026-10-29, with the answer recorded under Decisions, and resolved by [A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md), whose Changes item records it. Each rule joins its record's Decision with the implementation, as an edit in place once decision records are living topics.
