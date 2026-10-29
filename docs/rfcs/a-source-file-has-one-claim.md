---
id: a-source-file-has-one-claim
title: "A source file has one claim"
status: stable
describes: []
rfc_state: accepted
affects:
  - checks
  - context
  - change
  - frontmatter
resolved_by: docs/decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md
summary: A source file matched by two docs' describes is a certain error answered by narrowing the broader claim, a doc may exclude files from its own glob, and the specificity tie-break and two overlap hints go.
required_updates: []
weight: large
---

# A source file has one claim

## Summary

Every source file is claimed by exactly one doc, so there is one place to read about it and
no rule deciding which of two claims wins. A file that two docs' `describes:` both match
becomes an error that blocks, answered by narrowing the broader claim, and a doc may exclude
files from its own glob. This replaces three rules that disagree today. Two decisions, both
answered.

## Problem

Two docs may claim the same file today, and a "most specific claim wins" rule picks its
owner. The example the architecture doc gives: the planner's INDEX lists the file `entry.py`
in its routing folder, while the routing doc claims every Python file in that folder. Both
match `entry.py`, and the INDEX wins because an exact path outranks a glob. A reader of the
routing doc sees a glob that covers `entry.py` and cannot tell it belongs elsewhere.

Three rules govern that overlap, and they disagree. The tie-break allows it. One hint asks
overlapping docs to link each other. Another flags any wildcard in a parent that has
children, even one that overlaps nothing, while the uniqueness check's own example is a
parent wildcard over a child.

## How it works

**One claim per file.** A source file that two or more docs' `describes:` match is reported
as a certain error naming every doc and pattern, so CI blocks until it is fixed. The answer
is to narrow the broader claim to the files only it owns. Narrowing makes the tree more true
here: the other doc keeps the file, and a file left with no claim is caught by the error that
already reports an undocumented file.

**A doc can exclude.** A `describes:` entry starting with `!` removes files from that doc's
own claim, as `.gitignore` does. In the example, the routing doc keeps its glob and adds one
line excluding entry.py, so the carve-out stays one line instead of a list of every other file.

**What goes.** The specificity ranking, the tie-break, and both overlap hints. A wildcard
that overlaps no other claim is fine. Everything that asks who owns a file gets one answer,
or every claimant while an overlap error stands.

**What it cannot do.** A parent paragraph that describes a child's file in prose is still
review's job, since no check reads what a sentence means.

Not chosen: keeping the tie-break and reporting overlap as a hint; exact paths only, with no
globs.

## Cost and risk

Code shrinks: a ranking, two hints and their tests go, and one existing error widens. This
repository has no overlap today, 0 of its 141 source files. An adopter whose docs overlap gets
errors on upgrade, each fixed by narrowing or one exclusion line. An exclusion can leave a file
unclaimed, which the undocumented-file error then reports.

## Decisions

Answered by the owner on 2026-10-28:

1. **Exclusion entries are added**: a `!` entry in `describes:` removes files from its own
   doc's claim, so a carve-out is one line rather than a list that drifts as files are added.
2. **An overlap is an error from the first release**, since the fix is mechanical and the
   rule is single source of truth; no staged warning.

## Design detail

- **The code.** `uniqueness/duplicate-claim`, certain today for two claims at the same
  specificity, widens to every source file matched by two or more docs' `describes:`, whatever
  the specificity; no new code. The message names each doc and the pattern that matched. It is
  not drafts-exempt, since it is about a file outside the draft.
- **Specificity goes.** `specificity` and `Score` in `checks/uniqueness.py`, the
  `most_specific_claims` tie-break, and the glossary term *Specificity* are deleted.
  `claims_for` keeps returning every claimant. The callers that asked for the most specific
  owner take every claimant instead: `change/finalize.py`, `change/footprint.py`,
  `checks/co_change.py`, `context.py` (`_ownership_for_source_path` and the changed-claims
  path), `new/command.py` (`current_owners`), and `ownership_moves.py`, which
  `checks/diff_integrity.py` reads for a moved file's owners. `DocGraph.claims` in
  `docgraph.py` already returns every claim unranked and keeps only the `Score` shape. With
  one claimant, which is every file in a passing tree, nothing changes for them.
- **Exclusions** (decision 1a): a `describes:` entry that starts with `!` is a negated
  gitignore pattern; a doc's claim is its positive matches minus its negated ones, built as one
  `GitIgnoreSpec` per doc so negation follows gitignore order. The matching positive pattern is
  still reported per file, so messages keep naming a pattern. A negated entry that excludes
  nothing is not reported in this change.
- **Retired codes**, each with a tombstone in the resolving decision record, added in the
  change that removes the code:
  `uniqueness/unlinked-overlap` (an overlap is now an error, so linking cannot answer it) and
  `parent-child/wildcard-with-children` (a wildcard matters only when it overlaps).
- **Docs.** `docs/architecture/component-hierarchy.md` rewrites "Hierarchical Describes
  (Specificity Rule)" around one claim per file and the exclusion example;
  `docs/components/frontmatter.md` names the `!` form; `docs/components/checks.md` drops the
  two codes and its sentence that `claims_for` scores specificity; `docs/GLOSSARY.md` drops
  *Specificity*. The stable record `docs-are-atoms-in-six-layers-and-code-has-one-owner` says
  "otherwise the most specific claim wins". It resolves this RFC: at the second history reset
  its acceptance stated the one-claim rule there, as accepted and not yet implemented, and the
  implementation rewrites that sentence in place with a dated item.
- **The every-hint RFC** drops the two retired codes from its answers table.
- **Fixtures and tests.** The fixture repos that exercise specificity, and
  `tests/test_checks_uniqueness.py`, change to the one-claim rule; count them before starting.
  Re-check this repository's overlap count at implementation; it was 0 on 2026-10-28.

## Requirements

### Requirement: A file two docs claim is an error
ID: a-file-two-docs-claim-is-an-error
Provenance: code

`uniqueness` SHALL report `uniqueness/duplicate-claim` for each source file that the
`describes:` of two or more docs match, naming every such doc and the pattern that matched,
and SHALL NOT report a file exactly one doc's claim matches.

#### Scenario: A parent wildcard over a child's file
- **WHEN** `planner/INDEX.md` claims `app/planner/**` and `planner/routing.md` claims `app/planner/routing/entry.py`
- **THEN** the run reports `uniqueness/duplicate-claim` for `app/planner/routing/entry.py`, naming both docs

#### Scenario: A wildcard that overlaps nothing
- **WHEN** `planner/INDEX.md` claims `app/planner/*.py` and `planner/routing.md` claims `app/planner/routing/*.py`
- **THEN** the run reports no `uniqueness/duplicate-claim`

### Requirement: An exclusion removes files from its doc's claim
ID: an-exclusion-removes-files-from-its-docs-claim
Provenance: code

A `describes:` entry that starts with `!` SHALL remove the files it matches from its own
doc's claim, so they count toward neither that doc's ownership nor an overlap.

#### Scenario: A carve-out from a glob
- **WHEN** `planner/routing.md` claims `app/planner/routing/*.py` and `!app/planner/routing/entry.py`, and `planner/INDEX.md` claims `app/planner/routing/entry.py`
- **THEN** the run reports no `uniqueness/duplicate-claim`, and `irminsul context app/planner/routing/entry.py` names `planner/INDEX.md` as its owner

#### Scenario: An exclusion no other doc picks up
- **WHEN** that exclusion leaves `entry.py` claimed by no doc, in a covered directory
- **THEN** the run reports `uniqueness/undocumented-file` for it

### Requirement: Ownership has no tie-break
ID: ownership-has-no-tie-break
Provenance: code

Every reader that asks which doc owns a source file SHALL get every doc whose claim matches
it, with no ranking among them.

#### Scenario: Context during an overlap
- **WHEN** two docs claim `src/a.py` and `irminsul context src/a.py` runs
- **THEN** the packet names both docs as owners

## Tasks

- `T1` Widen `uniqueness/duplicate-claim` to every overlap and delete the specificity ranking
  and tie-break, with tests and the fixtures that used them. (req: a-file-two-docs-claim-is-an-error)
- `T2` Read `!` entries in `describes:` as exclusions, one spec per doc. (req: an-exclusion-removes-files-from-its-docs-claim)
- `T3` Move every owner lookup to all claimants. (req: ownership-has-no-tie-break)
- `T4` Retire `uniqueness/unlinked-overlap` and `parent-child/wildcard-with-children` with
  tombstones in the resolving decision record. (component: checks)
- `T5` Rewrite the specificity section of the architecture doc, the frontmatter and checks
  docs and the glossary, and drop the two codes from the every-hint RFC. (component: checks)

## Resolution

Accepted by the owner on 2026-10-29, with the answers recorded under Decisions, and resolved by
[Docs are atoms in six layers, and code has one owner](../decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md), which governs `checks/uniqueness.py` and states the one-claim rule as accepted and not
yet implemented beside the sentence it replaces, with a dated item under its Changes. The two
tombstones join that record's `retires:` in the change that removes the codes.
