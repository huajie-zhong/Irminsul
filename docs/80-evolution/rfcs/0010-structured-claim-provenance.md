---
id: 0010-structured-claim-provenance
title: Structured claim provenance
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0010: Structured claim provenance

## Summary

Force high-risk enforcement and automation claims into a structured shape that
can be checked mechanically. Free-form prose is still allowed, but stable
foundation and architecture docs must not casually claim that Irminsul blocks,
rewrites, generates, or guarantees behavior unless the claim has explicit state
and evidence.

## Motivation

Foundation docs are unusually dangerous when they rot. If a foundation doc says
"CI automatically rewrites old docs" or "the dashboard is generated daily," an
agent may treat that as a system guarantee even if the feature is only planned.

Plain prose is hard to verify. The solution is not to make a regex understand
every paragraph. The solution is to require risky claims to be declared in a
machine-readable form, then make prose point at those declarations.

## Detailed Design

### Structured Claims

Use a `claims:` frontmatter field or an `## Enforcement Claims` table. The first
implementation should prefer frontmatter because it is already parsed by
Irminsul.

Example:

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
| `external` | Enforced outside Irminsul. | Process, operation, or external tool doc. |

### `claim-provenance` Check

The check runs on stable docs in `00-foundation` and `10-architecture`.

It performs three deterministic validations:

1. Validate each structured claim has `id`, `state`, `kind`, `claim`, and
   `evidence`.
2. Validate every evidence path resolves and is appropriate for the claim state.
3. Scan body prose for high-risk terms such as `CI automatically`, `blocks`,
   `guarantees`, `rewrites`, `generated daily`, `nightly`, `auto-updates`,
   `enforces`, `cannot merge`, and `fails the build`.

If high-risk prose appears outside a structured claim reference, emit a warning.
If a structured claim is invalid or an `enabled` claim has no config or CI
evidence, emit an error.

### Structured Sections

Certain sections should require structured claims even if trigger vocabulary is
not present:

- `Mechanical Enforcement`
- `CI Pipeline`
- `Supersession Enforcement`
- `Health Dashboard`

This reduces false negatives from implied claims such as "old docs are kept in
sync with replacements."

### LLM Advisory Layer

Mechanical checks cannot reliably detect every implied overclaim. Add an
optional LLM advisory check that asks whether a paragraph claims current
automation or enforcement that the linked evidence does not support.

The LLM check emits info findings only. It never blocks a merge by default.

## Implementation Plan

1. Extend the frontmatter model to allow structured `claims` without requiring
   projects to use them outside protected layers.
2. Implement `claim-provenance` as a soft deterministic check.
3. Add fixtures for valid planned, implemented, available, enabled, and external
   claims.
4. Add fixtures for risky prose without claim references.
5. Add an LLM advisory check only after the deterministic shape is stable.
6. Update foundation docs to classify overclaimed mechanisms as implemented,
   available, enabled, planned, or external.

## Drawbacks

Fixed vocabulary can produce false positives and false negatives. The structured
section requirement reduces false negatives in the highest-risk docs. Initial
warning severity reduces the cost of false positives while the vocabulary is
tuned.

## Alternatives

- Rely on LLM checks only. This is broader but non-deterministic and cannot be a
  hard CI gate.
- Require every paragraph to cite evidence. This is too heavy for normal docs.
- Keep claims in prose and depend on review. That is the failure mode this RFC
  is intended to prevent.

## Unresolved Questions

- Should `claims` become a typed first-class frontmatter field or remain an
  allowed extension parsed only by this check?
- Should unstructured risky prose eventually become an error in stable
  foundation docs?
