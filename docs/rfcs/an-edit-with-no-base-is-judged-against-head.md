---
id: an-edit-with-no-base-is-judged-against-head
title: "An edit with no base is judged against HEAD"
status: stable
describes: []
rfc_state: implemented
affects:
  - context
  - checks
  - cli
  - mcp-server
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
adoption record lists needs a new doc. Two decisions, answered.

## Decisions

Answered by the owner on 2026-10-29:

1. **Judge uncommitted work against HEAD by default**, rather than keeping the run quiet until
   a base is given and only saying so.

Answered by the owner on 2026-11-25:

2. **A finding that waits for the commit's trailer does not fail the run.** In
   `context --after-edit`, a certain finding whose answer is a commit trailer, raised by work that is
   not committed yet, is reported with the trailer to write and does not fail the run.
   `check --diff` is the gate and is unchanged: it still fails on that finding until a commit
   carries the trailer.

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
- **A finding that waits for the commit's trailer.** Judging uncommitted work met a case the
  first decision did not settle. With `uniqueness` taken out of `checks.enabled` and not
  committed, the run failed with `diff-integrity/check-disabled`, a certain finding that only an
  `Irminsul-Reviewed` trailer answers, in the message of a commit that does not exist yet. Run
  as a pre-commit hook it could never pass.
- **The rule for it.** A finding waits when it is certain, its code declares the answer
  `trailer`, and it is about a file with uncommitted changes, which is the condition under
  which a trailer on an earlier commit lapses. The run lists it apart from the errors the change
  introduced, with its trailer, counts it as waiting and not as a new error, and does not fail
  on it. A finding about committed work alone still fails, because a commit could have carried
  its trailer. A hint that a trailer answers never failed the run and is listed as before.
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

### Requirement: A finding that waits for the commit's trailer does not fail the run
ID: a-finding-that-waits-for-the-commits-trailer-does-not-fail
Provenance: code

`context --after-edit` SHALL NOT count as a new error, and SHALL NOT fail on, a certain
finding whose code declares the answer `trailer` and that is about a file with uncommitted
changes. It SHALL report that finding apart from the errors the change introduced, with the
trailer to write, and SHALL say how many such findings wait. `check --diff` SHALL still fail
on the finding until a commit of the change carries the trailer.

#### Scenario: A check is disabled and the edit is not committed
- **WHEN** a check is removed from `checks.enabled`, the edit is not committed, and `context --after-edit` runs with no base
- **THEN** it exits 0 and lists `diff-integrity/check-disabled` apart from the new errors with its trailer, and `check --diff HEAD` on the same tree exits 1

#### Scenario: A waiting finding beside an ordinary new error
- **WHEN** the uncommitted work also introduces an error that no trailer answers
- **THEN** the run exits 1, counting one new error and one finding that waits

#### Scenario: The work is committed without the trailer
- **WHEN** the edit that removed the check is committed with no trailer, nothing is uncommitted, and `context --after-edit --base-ref <base>` runs
- **THEN** its change validation fails with `diff-integrity/check-disabled` as a new error

## Tasks

- `T1` Default the after-edit base to `HEAD` when none is given and the tree is dirty. (req: uncommitted-work-is-judged-against-head)
- `T2` Name the base in the output and drop the no-base note. (component: context)
- `T3` Leave a finding that waits for the commit's trailer out of the new errors and the exit code, and list it apart with its trailer. (req: a-finding-that-waits-for-the-commits-trailer-does-not-fail)

## Resolution

Accepted by the owner on 2026-10-29, with the answers recorded under Decisions, the second given on 2026-11-25, and resolved by [A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md), whose Changes items record them. Each rule joins its record's Decision with the implementation, as an edit in place once decision records are living topics.
