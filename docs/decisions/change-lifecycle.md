---
id: change-lifecycle
title: Change lifecycle
status: stable
describes: []
summary: RFCs move through four states bound to repository evidence, implemented records do not change until consolidated into ADRs, and retirements live as tombstones on stable ADRs.
retires:
  - id: split-rfc-checks
    kind: concept
    matches:
      - rfc-resolution
      - decision-updates
      - rfc-lifecycle-integrity
    guidance: Enable `rfc-lifecycle` and `rfc-follow-through` in checks.enabled.
---

# Change lifecycle

## Status

Accepted, 2026-09-12.

## Context

Significant change starts as an RFC, but an RFC that says "accepted" or "implemented"
is only useful if repository evidence can contradict it. Records also accumulate, and
most implemented proposals go on restating behaviour that has already shipped.

## Decision

- **Four states.** `rfc_state` is `draft`, `accepted`, `implemented`, or `rejected`.
  `change transition` applies a human decision to `accepted` or `rejected` and requires
  a resolving ADR for acceptance; `change finalize` is the only path to `implemented`
  and promotes code-backed requirements into owning component docs as anchored claims.
- **Evidence is derived, never stored.** Changed files, owners, tests, impact, and
  readiness come from the diff and the graph on every call. Reports may say a change is
  mechanically ready; they never say its behaviour is correct.
- **Behaviour-changing RFCs carry requirements and tasks.** Requirements have stable ids,
  SHALL/MUST text, and WHEN/THEN scenarios; tasks reference a requirement or component.
- **Decision updates follow the state.** An accepted RFC declares `required_updates`;
  the `implements` back-link is due only once it is implemented, because
  `rfc-lifecycle` rejects it earlier.
- **Implemented records do not change, then are consolidated.** Once the protected branch
  records an RFC as implemented, editing it is an error
  ([Git history seals implemented records](git-history-seals-implemented-records.md)), so an extension starts a
  new RFC. Periodically, in a change a person merges deliberately, implemented and rejected RFCs and the ADRs that resolved them are folded
  into themed decision records and removed; git history keeps the originals. Open
  proposals stay.
- **Relationships are forward-only.** `change graph` derives successors and dependencies
  from the newer RFC's declarations and never edits a predecessor.
- **Retirements are tombstones.** A stable ADR declares each retired command or concept
  with exact match phrases and guidance, and `retired-references` reports
  current guidance that still presents one as live, unless the phrase links to the ADR.
- **Integrity and follow-through are separate checks.** `rfc-lifecycle` holds what makes
  a record untrustworthy: a missing state, a dangling `resolved_by` or `implements`, or
  implementation evidence before finalization. `rfc-follow-through` holds outstanding
  work, some of which `irminsul fix` completes.
- **Every RFC declares its state.** `rfc-lifecycle` reports an RFC without `rfc_state`;
  nothing infers a state from status or repository evidence.

## Alternatives Considered

- **Separate decision and delivery enums.** Rejected: two fields invite contradictions.
- **Infer completion or shipping from changed code.** Rejected: touching an owner is not
  proof a requirement is met.
- **Keep every implemented RFC forever.** Rejected: the records come to outnumber the live
  docs while restating shipped behaviour; the decisions and rejected alternatives are
  what future contributors need, and consolidation keeps those.
- **Accept an edit to an implemented RFC when its record is updated to match.** Rejected:
  that turns enforcement into a formality.

## Consequences

- An RFC's state can be contradicted mechanically, so stale lifecycle metadata surfaces.
- Consolidation trades per-proposal detail in the tree for history in git.
