---
id: authority-follows-the-kind-of-claim
title: "Authority follows the kind of claim"
status: stable
describes: []
summary: Code is authoritative for mechanically reconstructable implementation state and not for intent, constraint, or rationale; a claim declares its relation to the evidence it cites, and that relation decides who wins a disagreement and what changing the claim means.
---

# Authority follows the kind of claim

## Status

Accepted, 2026-09-16. Scopes principle 4 in
[Principles](../foundation/principles.md), which is updated in place.

Implemented since acceptance: of what the Consequences list as not yet mechanical,
reading protection from the base claim and protecting a governing claim's text and
relation now run in `diff-integrity`, as the [checks component](../components/checks.md)
describes. Routing a diverged `review-on-divergence` claim to the review queue does not.

## Context

Two rules in this repository contradicted each other. [`principles.md`](../foundation/principles.md) said
"when code and docs disagree, code wins by default", while the agent entry point and the
[agent protocol](../guides/agent-protocol.md) said to decide which side is wrong first,
and that a sentence describing what the code *should* do is a bug to report rather than a
doc to rewrite.

Both cannot hold. Under "code wins", an agent that made `change transition` skip human
approval would be correcting the foundation rather than violating it — and the foundation
says agents operate while humans authorize. The philosophy had fallen behind the
implementation, which already treats some statements as binding on code.

Two further observations showed the fix is not simply reversing the rule.

The layer a document lives in does not determine what makes its sentences true.
[`enforcement.md`](../foundation/enforcement.md) carries `claim: This repository runs its enabled Irminsul
checks in CI`, citing the workflow, the config, and the pipeline. That is a report about
implementation state that happens to live in the normative layer; if CI stopped running
those checks, the claim would be stale, not the code defective. So folder paths cannot
serve as a type system.

And "anything that *can* be derived from code *should* be" is too broad. A sentence such
as "`context` is a stateless task-local projection of the repository knowledge graph" is
inferable from the code, in that a reader could reconstruct it by understanding enough of
the implementation. It is not mechanically reconstructable, and it is exactly the kind of
compression documentation exists to provide.

## Decision

- **Code is authoritative for mechanically reconstructable implementation state** — the
  facts a tool can rebuild without semantic judgment, such as command and option
  surfaces, signatures, config keys, and exports. Those are derived on demand and never
  hand-copied. Code is not authoritative for intent, constraint, semantic models, or
  rationale.
- **A claim declares its relation to the evidence it cites**, through a `relation` field
  with three values. The question it answers is operational — what happens when the claim
  and the evidence disagree — rather than what the claim is about:
  - `follows-evidence` — a report. The evidence wins; changing the claim is routine
    maintenance.
  - `review-on-divergence` — a semantic model. Neither side wins automatically; the
    divergence goes to a reader, and changing the claim is a semantic change to surface.
  - `governs-evidence` — a contract or invariant. The claim wins, so an implementation
    that violates it is suspect; changing the claim is a change of intent.
- **An omitted `relation` means `review-on-divergence`**: absent a declared authority,
  Irminsul refuses to infer a winner.
- **`follows-evidence` is reserved for reports that are expensive to derive.** Cheap
  mechanical state never becomes a claim at all — it becomes an `inventory:` entry, which
  is watched and derived, or it is left to be queried. A repository accumulating
  `follows-evidence` claims is materializing implementation state through the claims
  field.
- **Protection is read from the base version of a change**, never from the version under
  review, so a change cannot lower its own protection. Changing a governing claim's
  `relation` is itself a governing change.
- **Authorization is separate from relation.** The relation says what kind of change this
  is; whether that change is permitted comes from the same path that already excuses
  turning a check off — a stable decision record the same change adds, naming the subject
  in its `## Decision` section.
- **The enforcement mechanism is derived, never declared.** A `mechanism:` field would be
  metadata describing metadata, and would go stale exactly as the facts it described.
- **Protection follows relation, not layer.** A layer states why knowledge is presented
  where it is; it does not decide what makes a sentence true.

## Alternatives Considered

- **Keep "code wins by default".** Rejected: it licenses an implementation to overwrite a
  stated constraint, which makes the foundation advisory.
- **Invert it to "docs win".** Rejected: it licenses prose to contradict shipped
  behaviour, which is the rot this project exists to stop.
- **Derive authority from the document's layer.** Rejected on the counterexample above —
  descriptive claims live in `foundation/` and governing ones in `components/`.
- **Type the existing `kind` field instead of adding `relation`.** Rejected: `kind`
  records what a claim is about, which is orthogonal to who wins a disagreement. The same
  sentence can be a semantic model and a contract at once; forcing a single subject-matter
  label invites an ontology argument that the operational question avoids.
- **Declare authority and mechanism as their own fields.** Rejected: `relation` plus
  `authority` can contradict each other, and a declared mechanism duplicates what the tool
  already knows.
- **More than three relations.** Deferred: three are enough to test whether the model
  earns its place. If `review-on-divergence` proves too broad, it should be split from
  observed use rather than from theory.

## Consequences

- `Claim` gains a `relation` field. Existing claims keep working, because an omitted
  relation has defined meaning.
- What is enforced today is narrower than what this record describes. Already mechanical:
  the surfaces that must not be materialized (`liar`, `inventory-drift`, `code-references`),
  the sealing of accepted decisions and implemented RFCs, and one-owner-per-source-file.
  Not yet mechanical: reading protection from the base claim, protecting a governing
  claim's text and relation from silent rewriting, and routing a diverged
  `review-on-divergence` claim to the review queue. Those are the follow-up work this
  record authorizes, not behaviour it describes.
- A semantic claim can still gain a mechanical projection. `import-deps` already checks a
  declared `depends_on` against the imports a module actually has. The rule is not that
  semantic meaning is forever unverifiable, but that it stays authored: enforce whatever
  projection of it can be mechanized, and route the rest to judgment.
