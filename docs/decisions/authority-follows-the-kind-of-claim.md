---
id: authority-follows-the-kind-of-claim
title: "Authority follows the kind of claim"
status: stable
describes: []
summary: Code is authoritative for mechanically reconstructable state, not intent; a claim's relation decides who wins a disagreement, protection is read from the base, and a declaration about surviving code is not removed silently.
governs:
  - src/irminsul/checks/claim_provenance.py
  - src/irminsul/frontmatter.py#Claim
  - src/irminsul/frontmatter.py#ClaimRelationEnum
  - src/irminsul/frontmatter.py#ClaimStateEnum
  - src/irminsul/checks/diff_integrity.py#_removed_governance
  - src/irminsul/checks/diff_integrity.py#_rewritten_governing_claims
  - src/irminsul/checks/diff_integrity.py#_inventory_weakening
  - src/irminsul/checks/diff_integrity.py#_declared_now
  - src/irminsul/checks/diff_integrity.py#_evidence_exists
  - src/irminsul/checks/diff_integrity.py#_glob_matches_anything
  - src/irminsul/listing/review.py#_governing_claims_over_changed_code
  - src/irminsul/listing/review.py#_removed_sentences
---

# Authority follows the kind of claim

## Status

Accepted, 2026-10-28. Scopes principle 4 in [Principles](../foundation/principles.md).

## Context

"Code wins" licenses an implementation to overwrite a stated constraint: an agent that made
`change transition` skip human approval would be correcting the foundation, not violating it.
"Docs win" licenses prose to contradict shipped behaviour. A doc's layer does not settle it:
`enforcement.md` claims this repository runs its checks in CI, a report living in the normative
layer. And "derive whatever can be derived" is too broad: "`context` is a stateless projection
of the repository" can be inferred from the code but not rebuilt by a tool.

Every check asks whether what a doc says is true, so the cheapest repair is often to delete the
sentence, anchor or claim that raised a finding. Deleting documentation is right when the code
went too; removing a declaration about surviving code, or a contract together with its code, is
not.

A claim in a component doc was never re-asked at all, because evidence drift judged only the
foundation and architecture layers.

## Decision

- **Code is authoritative for mechanically reconstructable implementation state,** such as
  command surfaces, signatures, config keys and exports, which are derived and never
  hand-copied. It is not authoritative for intent, constraint, semantic models or rationale.
- **A claim declares its `relation` to its evidence**, which says who wins a disagreement:
  `follows-evidence`, a report the evidence overrules, changed routinely;
  `review-on-divergence`, a model where neither wins and a reader decides; `governs-evidence`,
  a contract the code must obey, whose change is a change of intent. An omitted `relation`
  means `review-on-divergence`: Irminsul infers no winner. `follows-evidence` is for reports
  that are expensive to derive; cheap state is an `inventory:` entry or a query.
- **Claims carry provenance.** `claim-provenance` requires evidence that exists, is
  repo-relative and fits the claim's `state`, reports a `<!-- claim:<id> -->` marker naming no
  declared claim, and reports evidence that changed after the doc as `evidence-drift`. An
  anchor pins its symbol's hash, and only a person re-pins it.
- **A pin acknowledges evidence drift.** While a file keeps its pinned hash `evidence-drift`
  skips it; once the hash differs the commit-time comparison applies, so a pin only ever
  removes drift.
- **Evidence drift is judged in every layer** (accepted, not yet implemented), landing after
  part pins exist.
- **A divergence goes to a reader.** `list review --changed` queues each claim other than a
  report whose evidence the change touched, asking under `governs-evidence` whether the code
  still obeys it and under `review-on-divergence` which side is wrong.
- **Protection is read from the base.** A claim that governed its evidence at the base and
  changed its sentence, evidence, state or kind, or stopped governing, is
  `diff-integrity/governing-claim-changed`, certain. Deleting it, renaming its id or deleting
  its doc is `diff-integrity/governing-claim-removed`, certain, even when its evidence is gone
  too, since that is the change a contract exists to stop. Any other claim whose sentence
  changed, a report apart, is `diff-integrity/claim-reworded`, a hint.
- **Other declarations about surviving code are not removed silently.** Certain:
  `diff-integrity/anchor-removed` while the anchored symbol still resolves;
  `diff-integrity/claim-removed` while all of the claim's evidence exists;
  `diff-integrity/inventory-removed` while the entry's source still matches files; and
  `diff-integrity/inventory-weakened` for an entry that keeps its kind and source but stops
  asking for explanation or completeness, or gains an `omit`. When the code went too, or the
  removed claim was a report, nothing is reported.
- **Moving is not removing.** A declaration is kept while any doc declares it, a claim by its id
  and sentence, so splitting a doc reports nothing.
- **Authorization is a decision record, separate from the relation.** A stable record the change
  adds, naming the claim id in a code span in its `## Decision`, excuses a claim's rewording or
  removal; one naming the doc's path excuses a weakened inventory entry. A removed anchor or
  inventory entry has no excuse: restore it, declare it elsewhere, or remove its code.
- **Deleted prose is queued, not blocked:** `list review --changed` lists it as
  `removed-sentence`.
- **The mechanism is derived, never declared, and protection follows relation, not layer.**
- **A trailer answers removing or weakening governance** (accepted, not yet implemented). A
  reworded or removed claim, a changed or removed governing claim and a weakened inventory entry
  are answered by a trailer naming the claim id or the doc's path, not by a decision record. A
  removed anchor whose symbol still resolves, named `path#symbol`, and a removed inventory entry
  whose source still matches, named `source#kind`, gain the same answer. A claim whose relation
  moves from `review-on-divergence` to `follows-evidence` is `diff-integrity/claim-downgraded`,
  a hint a trailer answers. This replaces "Authorization is a decision record" and "A removed
  anchor or inventory entry has no excuse" above.

## Alternatives Considered

- **Code wins, or docs win.** Rejected: the first makes the foundation advisory, the second
  licenses rot.
- **Authority from the layer.** Rejected: descriptive claims live in `foundation/`, governing
  ones in `components/`.
- **Type the `kind` field instead.** Rejected: what a claim is about is orthogonal to who wins.
- **`authority` and `mechanism` fields.** Rejected: they can contradict `relation`, and the tool
  already knows the mechanism.
- **More than three relations.** Deferred until use shows `review-on-divergence` is too broad.
- **Report everything present at the base and gone at the head.** Rejected: every honest
  cleanup would be an error.
- **Report removals as hints, or compare sentences and block deletions.** Rejected: a hint does
  not stop the cheapest green run, and no rule tells a deleted claim from a rewritten one.
- **Release a governing claim with its evidence, or require the evidence to survive.**
  Rejected: rewording would stay more protected than deleting, or governed code could never be
  rightly deleted.
- **Re-pin anchors during fixes.** Rejected: re-pinning says someone re-read the prose.
- **A pin that drifts whenever its hash differs.** Rejected: updating the doc beside its evidence
  would stop clearing the finding, and a Python that renders a syntax tree differently would
  report drift on unchanged evidence.
- **A trailer for `evidence-drift`.** Rejected: that finding runs without a range, where no
  trailers are read.

## Consequences

- Removing a feature with the contract that governed it takes a decision record in the same
  change. Whether its reasoning holds stays a review question.
- A semantic claim can gain a mechanical projection, as `import-deps` checks `depends_on`
  against imports; the rest goes to judgment.
- The removal rules need a diff range; a plain `irminsul check` relies on the ownership floor of
  [Docs are atoms in six layers, and code has one owner](docs-are-atoms-in-six-layers-and-code-has-one-owner.md).
- **Known limit:** a claim is kept by id and sentence alone, so a governing claim moved to
  another doc with its relation dropped or its evidence repointed is not reported.
- Once drift is judged in every layer, component claims start being re-asked; their whole-file
  pins re-ask on churn until they are narrowed.

## Changes

- 2026-10-28: Accepted [Claim evidence names a part](../rfcs/claim-evidence-names-a-part.md):
  evidence drift is judged in every layer.
- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  a trailer answers removing or weakening governance, and a claim downgrade is reported.
