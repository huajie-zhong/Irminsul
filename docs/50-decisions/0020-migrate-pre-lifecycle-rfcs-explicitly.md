---
id: 0020-migrate-pre-lifecycle-rfcs-explicitly
title: "ADR-0020: Migrate pre-lifecycle RFCs explicitly"
audience: adr
tier: 2
status: stable
describes: []
summary: Preserve historical RFC truth through explicit, evidence-backed lifecycle classification.
---

# ADR-0020: Migrate pre-lifecycle RFCs explicitly

## Status

Accepted, 2026-07-15. Resolves
[`0041-pre-lifecycle-rfc-migration`](../80-evolution/rfcs/0041-pre-lifecycle-rfc-migration.md).

## Context

RFCs written before Irminsul's structured lifecycle can be valid documents while
remaining invisible to normal lifecycle commands. Their prose, links, Git history,
and apparent implementation provide useful evidence, but none reliably establishes
whether a human accepted, implemented, rejected, or left the proposal in draft.

Silently assigning a default would make repository knowledge look more certain than
its provenance permits. Requiring hand-edited YAML instead would give agents no safe
inventory, validation, preview, or atomic write path.

## Decision

Add `irminsul change migrate` as an explicit, one-RFC-at-a-time migration workflow.
The read path inventories candidates and presents their evidence without recommending
a state. The write path requires a human-selected lifecycle state, previews the exact
plan by default, validates state-specific evidence, and writes only after confirmation.

Record typed migration provenance on every migrated RFC. Historical implementation
requires a separate human attestation and is permanently distinguishable from normal
anchor-backed finalization. Expose every unclassified RFC through lifecycle integrity
and the maintenance queue until a human resolves it.

## Alternatives Considered

- **Infer state from document status, links, history, or code.** Rejected because
  those signals cannot prove intent or approval.
- **Mark every legacy RFC as draft.** Rejected because a convenient default would
  overwrite historical truth and hide unresolved classification work.
- **Support bulk migration first.** Rejected because classification authority is
  per proposal; batching before individual plans are approved increases review risk.
- **Require manual frontmatter edits.** Rejected because it provides no consistent
  evidence packet, validation, provenance, preview, or atomicity.

## Consequences

- Agents can discover and prepare legacy lifecycle work without claiming authority
  over its outcome.
- Humans must classify legacy RFCs individually; Irminsul's own backlog remains
  visible until those decisions are made.
- Attested historical implementation is intentionally weaker than normal finalization
  and remains labeled as such.
- Lifecycle checks gain non-blocking migration warnings while retaining hard errors
  for contradictory or corrupted records.
