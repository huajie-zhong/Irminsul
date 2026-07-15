---
id: 0016-freeze-implemented-rfc-records
title: "ADR-0016: Freeze implemented RFC records"
audience: adr
tier: 2
status: stable
describes: []
summary: Seal implemented RFCs with an enforced full-file SHA-256 and treat extensions as new RFCs.
---

# ADR-0016: Freeze implemented RFC records

## Status

Accepted, 2026-07-15. Resolves
[`0022-universal-fix-coverage`](../80-evolution/rfcs/0022-universal-fix-coverage.md),
[`0027-watched-surfaces`](../80-evolution/rfcs/0027-watched-surfaces.md),
[`0029-bound-change-loop`](../80-evolution/rfcs/0029-bound-change-loop.md),
[`0030-rfc-requirements-and-scenarios`](../80-evolution/rfcs/0030-rfc-requirements-and-scenarios.md),
[`0031-change-tasks-and-apply`](../80-evolution/rfcs/0031-change-tasks-and-apply.md),
[`0032-implementation-finalization-and-anchoring`](../80-evolution/rfcs/0032-implementation-finalization-and-anchoring.md),
[`0033-derived-layered-impact`](../80-evolution/rfcs/0033-derived-layered-impact.md),
[`0034-binding-readiness-and-agent-lifecycle`](../80-evolution/rfcs/0034-binding-readiness-and-agent-lifecycle.md),
and [`0035-rfc-lifecycle-integrity-and-frozen-records`](../80-evolution/rfcs/0035-rfc-lifecycle-integrity-and-frozen-records.md).

## Context

The watched-surface implementation and the bound-change stack were merged to
`main`, but their RFC metadata remained draft. Existing checks did not detect that
contradiction. The now-shipped finalization command also left implemented RFC prose
mutable, allowing a later edit to change the apparent contract without a new review.

## Decision

Record RFCs 0022, 0027, and 0029 through 0034 as implemented. Add RFC 0035 as the new
proposal governing lifecycle integrity instead of extending the already-shipped RFC
0034. Every implemented RFC receives a `frozen_hash` containing a full SHA-256 over
the normalized file except for the seal line itself.

Register lifecycle-integrity as a hard check. A mismatched or premature seal and an
explicit implementation backlink before finalization are errors. Missing seals on
legacy implemented RFCs and stable live docs linking draft RFCs are warnings with
actionable lifecycle queue entries. Finalization writes the seal last.

## Alternatives Considered

- **Extend RFC 0034.** Rejected because 0034 describes shipped behavior and should
  remain a historical proposal, not absorb a new enforcement contract.
- **Leave the shipped RFCs draft.** Rejected because the state would contradict the
  implementation and keep them invisible to the accepted-work queue.
- **Depend only on Git.** Rejected because CI would not reject modified history.
- **Make every migration gap an immediate error.** Rejected because existing
  repositories need a warning-and-fix path for implemented RFCs created before seals.

## Consequences

- Implemented RFC records are immutable under the hard profile.
- Changes to shipped behavior start with a new RFC and may supersede or extend the
  live specification without rewriting the old proposal.
- The lifecycle queue includes draft-but-presented-as-live and unsealed-history debt.
- RFC 0027 remains valid and is now recorded as implemented; RFC 0023 remains draft
  and is modernized separately around ADR reviewability rather than obsolete lifecycle
  assumptions.
