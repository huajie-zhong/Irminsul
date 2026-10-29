---
id: a-change-to-the-foundation-asks-for-the-owners-sign-off
title: "A change to the foundation asks for the owner's sign-off"
status: stable
describes: []
rfc_state: accepted
affects:
  - checks
resolved_by: docs/decisions/a-change-may-not-lower-its-own-gates.md
summary: A pull request that edits the body of a foundation doc gets a hint that a commit trailer answers, so a principle or non-goal is never changed in passing by a feature branch.
required_updates: []
weight: small
---

# A change to the foundation asks for the owner's sign-off

## Summary

When a change edits a foundation doc's text, the pull request run says so, and the owner's
sign-off in a commit trailer answers it. In the 2026-10-29 dogfood an agent narrowed the
project's "budgets" non-goal itself to fit the feature it was building, and nothing noticed.
One decision, answered.

## Decisions

Answered by the owner on 2026-10-29:

1. **A hint under `check --diff`, answered by a trailer**, rather than no signal.

## Design detail

- **The finding.** `diff-integrity/foundation-changed`, a hint at warning, under `--diff`, for
  each doc in the foundation layer whose body prose differs between the merge base and the
  working tree. A change to frontmatter alone, such as a re-pin, is not reported. A new
  foundation doc is reported too, since it adds a principle.
- **The answer.** `Irminsul-Reviewed: foundation-changed <path> reason="..."`, through the one
  acknowledgement step of `every-warning-hint-has-an-answer`, which this waits for; until then
  only the trailers of `co-change` and `evidence-drift` are read.
- **Not chosen.** A certain finding: an agent cannot honestly answer it, and the owner's
  answer is the trailer anyway. Blocking only `## Non-goals`: every principle binds.
- **Evidence.** Agent D's commit in the dogfood repo, which edited
  `docs/foundation/principles.md` inside a feature branch.
- **Governing record.** `a-change-may-not-lower-its-own-gates`, which governs the
  `diff-integrity` seals.

## Requirements

### Requirement: A foundation edit is reported under a diff
ID: foundation-edit-is-reported
Provenance: code

Under `--diff`, a change whose working tree holds a foundation doc whose body prose differs
from the merge base SHALL be reported as `diff-integrity/foundation-changed`, a hint, naming
the doc; a change to its frontmatter alone SHALL NOT be.

#### Scenario: A non-goal narrowed
- **WHEN** a branch edits a sentence under `## Non-goals` in `docs/foundation/principles.md`
- **THEN** `check --diff` reports `diff-integrity/foundation-changed` for that doc

#### Scenario: A re-pin only
- **WHEN** a branch changes only a claim's pin in a foundation doc's frontmatter
- **THEN** `check --diff` reports no `diff-integrity/foundation-changed`

## Tasks

- `T1` Report a foundation body edit under `--diff`. (req: foundation-edit-is-reported)
- `T2` Declare its answer as a trailer once the acknowledgement step exists. (component: checks)

## Resolution

Accepted by the owner on 2026-10-29, with the answer recorded under Decisions, and resolved by [A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md), whose Changes item records it. Each rule joins its record's Decision with the implementation, as an edit in place once decision records are living topics.
