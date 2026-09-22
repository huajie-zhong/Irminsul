---
id: removing-a-claim-about-surviving-code-is-a-finding
title: "Removing a claim about surviving code is a finding"
status: stable
describes: []
summary: Deleting an anchor, a claims entry, or an inventory entry is an error when the code it named still exists, and reported not at all when that code went away in the same change.
---

# Removing a claim about surviving code is a finding

## Status

Accepted, 2026-09-15. Builds on
[Unclaimed code in documented territory is an error](unclaimed-code-in-documented-territory-is-an-error.md).

## Context

Every check asked whether what a doc says is true. None asked whether it still says
anything. So for most findings the cheapest repair was not to correct the documentation
but to delete the sentence, the anchor, or the claim that raised it — and the result
passed, because there was nothing left to be wrong.

Deleting 42 of the 55 lines of a component doc, every claim and its anchor among them,
left `irminsul check --strict` exiting 0. Deleting the *file* produced six errors. The
incentive pointed at hollowing documents out rather than removing them.

The difficulty is that deleting documentation is often right. When code is deleted, the
prose about it should go too, and a rule that simply forbade removal would turn every
honest cleanup into an error to be silenced with an ignore comment — teaching exactly the
habit this is meant to prevent, and ratcheting docs toward describing code that no longer
exists.

The distinction that does hold: removing a claim is fine, and removing a claim *about code
that is still there* is not.

## Decision

- **A declaration removed while what it named survives is a certain finding**, reported by
  `diff-integrity` under a diff range. Three declarations count, because each is a doc
  asking to be told about specific code: an `<!-- anchor: -->` marker, a `claims:` entry,
  and an `inventory:` entry.
- **The same removal is reported not at all when the code went away too.** An anchor whose
  symbol no longer resolves, a claim whose evidence files are gone, an inventory entry
  whose source is gone: nothing is reported, because the doc is right to stop describing
  what does not exist. Deleting the code in the same change is the release valve, and it
  needs no ignore comment.
- **Deleted prose is queued, not blocked.** A sentence is not a declaration, and no rule
  can decide whether removing one was right, so `irminsul list review --changed` lists it
  with a `removed-sentence` marker for a reader to judge. That follows
  [Derive, don't materialize](derive-dont-materialize.md): the semantic question goes
  to a person, not to a check.

## Alternatives Considered

- **Anything present at the merge base and gone at head is an error.** Rejected: it makes
  every legitimate cleanup an error, it can only ratchet governance upward, and it says
  nothing about a doc that never carried a declaration.
- **Report removals as hints.** Rejected: a hint does not fail a run, and the whole
  problem is that this path was the cheapest way to a green run.
- **Compare prose sentences and block on deletions.** Rejected: it cannot tell a deleted
  claim from a rewritten one, and blocking on a judgment the tool cannot make is how a
  check earns an ignore comment.

## Consequences

- Removing an anchor or a claim now requires saying, through the diff itself, that the code
  went with it. A deliberate removal of documentation that keeps the code needs an
  `irminsul:ignore` comment with a reason, which is the reviewable record.
- The rule needs a diff range, so it runs on pull requests and not on a plain
  `irminsul check`. The floor that does run everywhere is the ownership rule in
  [Unclaimed code in documented territory is an error](unclaimed-code-in-documented-territory-is-an-error.md).
- Splitting a doc moves declarations between files. `--split-from` and the ownership-move
  reporting already describe that case; a declaration that reappears in another doc in the
  same change is still reported here, and is the one case expected to carry a reason.
