---
id: 0021-derive-rfc-relationship-graphs
title: "ADR-0021: Derive RFC relationship graphs"
audience: adr
tier: 2
status: stable
describes: []
summary: Derive lifecycle-aware RFC relationships from forward declarations without mutating frozen predecessors.
---

# ADR-0021: Derive RFC relationship graphs

## Status

Accepted, 2026-07-16. Resolves
[`0042-rfc-dependency-and-supersession-graphs`](../80-evolution/rfcs/0042-rfc-dependency-and-supersession-graphs.md).

## Context

Agents can inspect an RFC's lifecycle and generic backlinks, but cannot directly
answer which proposals block it, what depends on it, whether a replacement is
planned or effective, or whether the authored relations contain contradictions.

The existing generic supersession repair writes a reverse `superseded_by` pointer
onto the predecessor. That is useful for ordinary evolving documents but conflicts
with implemented RFCs, whose sealed historical record must not be rewritten when a
new successor is proposed.

## Decision

Add `irminsul change graph [<rfc>]` as a deterministic, read-only projection over
the existing RFC `depends_on` and `supersedes` declarations. Derive reverse
successors from the newer RFC's forward declaration. Include pre-lifecycle RFCs
without inferring their state, retain unresolved targets as evidence, and expose
cycles, self-reference, multiple effective successors, and implementation-order
contradictions in stable plain and JSON output.

Exclude RFC records from the generic reciprocal supersession repair path. Ordinary
documents retain its existing behavior; RFC replacement remains forward-only so an
implemented predecessor stays byte-for-byte frozen.

Keep the query observational. Relationship problems remain visible with exit zero;
unknown focus and malformed options remain usage errors. A later decision may
promote selected contradictions into lifecycle gates after the read contract has
been exercised.

## Alternatives Considered

- **Add RFC-specific relationship fields.** Rejected because it would duplicate
  existing authored relationships and create reconciliation work.
- **Write `superseded_by` onto old RFCs.** Rejected because reverse edges are
  derivable and implemented RFCs are immutable.
- **Infer missing lifecycle state from graph context.** Rejected because a
  relationship does not establish human intent or approval.
- **Make contradictions hard errors immediately.** Deferred so agents can first
  observe and repair existing graphs through a stable read surface.
- **Use generic backlinks alone.** Rejected because they merge edge types and do
  not interpret lifecycle readiness or supersession effectiveness.

## Consequences

- Agents receive one query for repository-wide or focused RFC planning context.
- Frozen predecessors never require a reverse metadata edit when superseded.
- Dangling and contradictory relationships remain inspectable without preventing
  the inspection command itself from running.
- Generic non-RFC dependencies and supersession repair keep their existing meaning.
- Transition and finalization gates do not yet enforce graph issue policy.
