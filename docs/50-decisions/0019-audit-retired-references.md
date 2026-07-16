---
id: 0019-audit-retired-references
title: "ADR-0019: Audit retired references from decision-owned tombstones"
audience: adr
tier: 2
status: stable
describes: []
summary: Keep retirement provenance in stable ADRs and audit current guidance with deterministic exact matching.
---

# ADR-0019: Audit retired references from decision-owned tombstones

## Status

Accepted, 2026-07-15. Resolves
[`0040-retired-reference-audit`](../80-evolution/rfcs/0040-retired-reference-audit.md).

## Context

Current surface derivation shows which commands exist, but a missing identity
does not reveal whether it was intentionally removed, renamed, or accidentally
lost. Historical ADRs explain those choices, while current stable guidance can
continue teaching obsolete commands and concepts long after their code is gone.

## Decision

Store typed retirement tombstones on the stable ADR that approved each removal.
Require a canonical live-surface identity for CLI commands, exact visible match
phrases, and actionable guidance. Audit current guidance deterministically and
allow historical use only when the exact phrase links to its owning ADR.

Use live CLI derivation only to disprove a retirement: if the identity exists
again, warn on the ADR and disable its tombstone. Do not infer retirement from
absence, Git history, or approximate prose similarity.

## Alternatives Considered

- **Infer removals from Git history.** Rejected because deletion has no durable
  intent, ownership, or replacement guidance.
- **Store a term list in configuration.** Rejected because configuration is not
  the human-approved decision record for a lifecycle event.
- **Reuse terminology-overload.** Rejected because ambiguity and retirement have
  different provenance, exemptions, and remediation.
- **Use fuzzy matching.** Rejected because false positives would train agents to
  ignore the audit; explicit aliases keep results explainable.

## Consequences

- Stable ADRs become the durable provenance for removed public knowledge.
- Current examples and prose receive actionable warnings when they teach retired
  surfaces.
- Restored CLI commands contradict stale retirement metadata visibly.
- Teams must backfill precise aliases for retirements that predate this field.
