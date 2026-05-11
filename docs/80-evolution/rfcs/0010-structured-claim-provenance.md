---
id: 0010-structured-claim-provenance
title: Structured claim provenance
audience: explanation
tier: 2
status: stable
describes: []
---

# RFC 0010: Structured claim provenance

## Summary

Force high-risk enforcement and automation claims into a structured shape that
can be checked mechanically. Free-form prose is still allowed, but stable
foundation and architecture docs must not casually claim that Irminsul blocks,
rewrites, generates, or guarantees behavior unless the claim has explicit state,
inline prose references, and evidence.

## Motivation

Foundation docs are unusually dangerous when they rot. If a foundation doc says
"CI automatically rewrites old docs" or "the dashboard is generated daily," an
agent may treat that as a system guarantee even if the feature is only planned.

Plain prose is hard to verify. The solution is not to make a regex understand
every paragraph. The solution is to require risky claims to be declared in a
machine-readable form, then make prose point at those declarations.

## Design

### Structured Claims

Claims are stored in the frontmatter of the doc that makes the assertion:

```yaml
claims:
  - id: supersession-auto-update
    state: planned
    kind: auto_fix
    claim: Supersession auto-update will mark old docs deprecated.
    evidence:
      - docs/80-evolution/rfcs/0002-fix-and-regen-typescript.md
```

Valid states:

| State | Meaning | Required evidence |
|---|---|---|
| `implemented` | Code exists, but may not be enabled by default. | Source path or component doc. |
| `available` | Implemented and user-enabled by config or CLI. | Implementation evidence plus enablement docs. |
| `enabled` | Active in this repo's default config or CI. | Config, action, or workflow evidence. |
| `planned` | Proposal only. | RFC link. |
| `external` | Enforced outside Irminsul. | Process, operation, external-tool, or config doc. |

The frontmatter schema owns the claim shape. Missing fields, invalid states,
empty evidence, or duplicate claim IDs are frontmatter errors.

### Prose References

High-risk prose must reference a structured claim in the same paragraph with an
inline marker:

```md
Hard checks block violating PRs. <!-- claim:hard-checks-enabled -->
```

The marker may be visible text or an HTML comment. Unknown `claim:<id>` markers
warn because they imply a structured claim that does not exist.

### `claim-provenance` Check

`claim-provenance` is a soft deterministic check. It runs on stable,
non-generated docs in `00-foundation` and `10-architecture`.

It emits errors when:

- evidence paths are absolute, missing, or do not resolve in the repo
- a claim has no evidence appropriate for its state
- an `enabled` claim has no config, action, or workflow evidence

It emits warnings when:

- high-risk prose appears without an inline `claim:<id>` reference
- a protected section has no structured claim reference
- a claim cites evidence changed after the claiming doc was last committed
- a `planned` claim cites an RFC marked accepted, rejected, or withdrawn

Protected section headings are:

- `Mechanical Enforcement`
- `CI Pipeline`
- `Supersession Enforcement`
- `Health Dashboard`

### Planned-to-Implemented Lifecycle

A planned claim is valid only while it points at an in-flight RFC. When an RFC
is resolved, the implementer updates affected claims in the same PR:

- `planned` becomes `implemented`, `available`, or `enabled`
- RFC-only evidence is replaced or supplemented with source, config, CI, or user
  documentation evidence
- rejected or withdrawn claims are removed or reworded

The implementer may be a human or an AI agent. The invariant is PR-level: the
code/config/doc change that resolves the RFC must also update structured claims.
If that step is missed, `claim-provenance` warns on the stale planned claim once
the cited RFC has `rfc_state: accepted`, `rejected`, or `withdrawn`.

### RFC Lifecycle Metadata

RFC docs may declare:

```yaml
rfc_state: draft
resolved_by: docs/50-decisions/0001-example.md
```

Valid `rfc_state` values are `draft`, `open`, `fcp`, `accepted`, `rejected`, and
`withdrawn`. `resolved_by` is required when `rfc_state: accepted`.

Existing RFCs do not need immediate metadata cleanup unless they are used as
planned-claim evidence.

## Implementation Plan

1. Extend the frontmatter model with typed `claims`, `rfc_state`, and
   `resolved_by`.
2. Implement `claim-provenance` as a soft deterministic check.
3. Add fixtures for valid planned, implemented, available, enabled, and external
   claims.
4. Add fixtures for risky prose without claim references.
5. Add git-backed drift tests for evidence newer than the claim doc.
6. Update foundation docs to classify overclaimed mechanisms as implemented,
   available, enabled, planned, or external.

## Drawbacks

Fixed vocabulary can produce false positives and false negatives. The structured
section requirement reduces false negatives in the highest-risk docs. Initial
warning severity reduces the cost of false positives while the vocabulary is
tuned.

Evidence drift can be noisy for broad source files. Authors should cite the
smallest source, config, or workflow evidence that supports the claim.

## Alternatives

- Rely on LLM checks only. This is broader but non-deterministic and cannot be a
  hard CI gate.
- Require every paragraph to cite evidence. This is too heavy for normal docs.
- Keep claims in prose and depend on review. That is the failure mode this RFC
  is intended to prevent.
