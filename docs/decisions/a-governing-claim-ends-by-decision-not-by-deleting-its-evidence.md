---
id: a-governing-claim-ends-by-decision-not-by-deleting-its-evidence
title: "A governing claim ends by decision, not by deleting its evidence"
status: stable
describes: []
summary: Removing a claim that governed its evidence at the base of a change is a certain finding even when the evidence is deleted too; only a decision record in the same change ends the contract.
---

# A governing claim ends by decision, not by deleting its evidence

## Status

Accepted, 2026-09-17. Qualifies the release valve of
[Removing a claim about surviving code is a finding](removing-a-claim-about-surviving-code-is-a-finding.md)
for claims that govern their evidence; that record stands for every other declaration.

## Context

[Removing a claim about surviving code is a finding](removing-a-claim-about-surviving-code-is-a-finding.md)
made deleting a claim an error while its evidence survives, and nothing at all when the
evidence is deleted in the same change, because a doc is right to stop describing code that
is gone.

[Authority follows the kind of claim](authority-follows-the-kind-of-claim.md) then gave
claims a relation, and a `governs-evidence` claim became a contract: rewording it, repointing
its evidence, or downgrading its relation is a change of intent that needs a decision record.
Deletion stayed under the older rule, so the protection was lopsided:

1. A component doc declares `widget-stateless`, governing `src/widget.py`.
2. A change rewords the claim to allow state: certain finding.
3. A change instead deletes the claim and `src/widget.py` together: nothing is reported.

The cheapest way past a contract was to delete it together with the code it governed, which
is the very change the contract exists to stop.

## Decision

- **A claim that governed its evidence at the base cannot be removed silently.** Deleting
  it, renaming its id, or deleting the doc that held it is a certain
  `diff-integrity/governing-claim-removed` finding under a diff range, whether or not its
  evidence still exists.
- **Protection is read from the base.** A change that downgrades the relation in one commit
  and deletes the claim in a later one is judged against the claim as it was before either.
- **A decision record ends the contract.** A stable decision record added in the same change
  that names the claim in a code span in its `## Decision` section excuses the removal, the
  same authorization a governing claim's rewording already needs.
- **Moving is not removing.** A claim that keeps its id and wording in another doc of the
  tree still governs, so splitting or moving a doc reports nothing.
- **Other declarations keep the release valve.** An anchor, an inventory entry, and a claim
  that does not govern its evidence are still released by deleting what they named.

## Alternatives Considered

- **Keep the release valve for governing claims.** Rejected: it leaves the bypass above
  open, and rewording would stay more protected than deleting.
- **Report the removal as a hint.** Rejected: a hint does not fail a run, and the bypass is
  exactly a path to a green run.
- **Require the evidence to survive.** Rejected: code a contract governs is sometimes
  rightly deleted, and forcing it to stay would block honest removals outright.

## Consequences

- Removing a feature together with the contract that governed it now takes a decision
  record in the same change. That is deliberate friction: the record is where a person says
  the contract ended, and there is no route that avoids writing it.
- The decision record's `## Decision` must name the claim id in a code span. Naming a check
  or a doc is not enough, and editing an existing record does not count.
- What the check can prove is only that the claim was removed without a record. Whether
  the record's reasoning is sound, and whether the code that replaced the old code honours
  the old contract, stay review questions.
