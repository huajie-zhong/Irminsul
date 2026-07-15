---
id: 0017-standardize-adr-structure
title: "ADR-0017: Standardize ADR structure without deriving lifecycle state"
audience: adr
tier: 2
status: stable
describes: []
implements:
  - 0023-adr-template-structure
summary: Require a reviewable ADR shape while keeping RFC lifecycle state in structured metadata.
---

# ADR-0017: Standardize ADR structure without deriving lifecycle state

## Status

Accepted, 2026-07-15. Resolves
[`0023-adr-template-structure`](../80-evolution/rfcs/0023-adr-template-structure.md).

## Context

ADR bodies in the repository do not consistently expose status and alternatives,
and the generator creates only Context, Decision, and Consequences. The original RFC
0023 draft justified a common shape as input to lifecycle checks. Later lifecycle
work moved that authority into `rfc_state`, `resolved_by`, `required_updates`, and
explicit graph links, so parsing ADR prose for state would now duplicate and weaken
the model.

The remaining problem is reviewability. A valid ADR can omit its decision, repeat a
section, or leave a placeholder while still passing frontmatter validation.

## Decision

Standardize ADRs on Status, Context, Decision, Alternatives Considered, and
Consequences. Generate that shape from `irminsul new adr` and the bundled init and
seed scaffolds, and add the soft deterministic `adr-structure` check for missing or
duplicate required sections and empty or placeholder-only decisions.

Treat the body Status as a human-readable summary only. The check does not infer or
validate RFC lifecycle state from ADR prose, and the generator does not add empty
relationship fields that imply lifecycle evidence where none exists.

## Alternatives Considered

- **Keep the old lifecycle-derived rationale.** Rejected: it creates two possible
  authorities for state and makes prose parsing load-bearing.
- **Make structural compliance a hard error immediately.** Rejected: a soft warning
  provides migration signal without breaking repositories that use a different ADR
  convention.
- **Only improve the template.** Rejected: existing and hand-written ADRs would keep
  drifting, and duplicate or placeholder decisions would remain invisible.
- **Attempt semantic scoring of Decision prose.** Rejected: deterministic checks can
  recognize absence and known placeholders, not whether a decision is wise or true.

## Consequences

- New ADRs begin with a predictable, reviewable outline.
- Configured checks expose incomplete and ambiguous ADR structure as warnings.
- Existing decisions receive a small, content-preserving section backfill.
- Lifecycle commands and metadata remain the sole authority for RFC state.
