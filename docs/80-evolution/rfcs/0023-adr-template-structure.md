---
id: 0023-adr-template-structure
title: ADR template and structured decision record
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: implemented
affects:
- checks
- new-list-regen
- seed
resolved_by: docs/50-decisions/0017-standardize-adr-structure.md
required_updates:
- path: docs/20-components/checks.md
  reason: Document the ADR structure check and its review-quality boundary
  kind: update
- path: docs/20-components/new-list-regen.md
  reason: Document the complete ADR scaffold emitted by irminsul new adr
  kind: update
- path: docs/20-components/seed.md
  reason: Keep seeded decision records compliant with the canonical ADR shape
  kind: update
frozen_hash: "sha256:c907020f843bedc58eb3ab34655f52ea9f2a52c1bd82d0219827f7c3f4aa997a"
---

# RFC 0023: ADR template and structured decision record

## Summary

Standardize the shape of architecture decision records so reviewers can find the
decision, alternatives, and consequences in a predictable place. Two changes ship
together: `irminsul new adr` emits the complete shape, and a soft deterministic
`adr-structure` check warns when an ADR is structurally unreviewable.

The check supports decision quality; it does not infer lifecycle state from prose.
RFC lifecycle authority remains in structured fields such as `rfc_state`,
`resolved_by`, `required_updates`, and explicit graph links.

## Motivation

The original draft assumed lifecycle checks needed to read an ADR's `## Status`
line and treat `implements:` as the authoritative RFC state transition. That is no
longer the architecture. The lifecycle work introduced after this RFC keeps state
and transition evidence in structured metadata and commands, where it can be
validated without interpreting prose.

ADR structure is still valuable for a different reason: the repository's decision
records vary, the generator omits `## Status` and `## Alternatives Considered`, and
nothing catches an absent, duplicated, or placeholder-only `## Decision`. A record
can therefore satisfy frontmatter checks while remaining difficult or impossible to
review. A predictable body shape gives authors a useful scaffold and gives reviewers
a small deterministic signal without pretending to judge the decision's semantics.

## Detailed Design

### Canonical ADR shape

Every document with `audience: adr` has one level-two section for each of:

- `## Status` - the human-readable decision disposition and date;
- `## Context` - the situation and constraints that require a decision;
- `## Decision` - the concrete choice in active voice;
- `## Alternatives Considered` - viable options and why they were not chosen;
- `## Consequences` - benefits, costs, risks, and follow-up work.

Heading matching is case-insensitive for migration compatibility, while the template
uses the canonical casing. Only parsed level-two headings count, so a heading quoted
inside a fenced example cannot accidentally satisfy the rule.

### Soft deterministic check

The `adr-structure` check runs only for `audience: adr` documents and emits warnings
for:

- a missing required section;
- more than one instance of a required section; or
- an empty or known placeholder-only `## Decision` section.

The last rule is deliberately narrow. It catches empty scaffolds and deterministic
placeholders such as `TODO` or `TBD`; it does not score prose, require a minimum word
count, or claim that a non-empty decision is correct. Duplicate findings point at the
second heading so an editor can jump directly to the ambiguous structure.

The check ships in `SOFT_REGISTRY`. Projects can promote configured warnings with
`--strict`; making the check hard by default remains a separate compatibility
decision under the RFC 0008 warning policy.

### Template and migration

`irminsul new adr` and the bundled init and seed ADR scaffolds emit all five
headings and initialize proposed records' `## Status` to `Proposed.`. They do not add
empty lifecycle backlink fields: lifecycle state is maintained through the RFC
lifecycle metadata and explicit decision records, not by making every ADR carry
ceremonial empty lists.

Existing ADRs are backfilled only where the repository survey found missing
sections. ADR 0001's alternatives heading is normalized to canonical casing. The
migration changes no recorded decisions.

### Lifecycle boundary

`## Status` is a readable summary for people. `## Decision` is the reviewed choice.
Neither is parsed to decide whether an RFC is draft, accepted, implemented, or
rejected. The lifecycle graph continues to use `rfc_state`, `resolved_by`,
`required_updates`, and explicit links. This prevents the structure check from
becoming a second, prose-derived lifecycle engine.

## Requirements

### Requirement: Complete ADR scaffold
ID: complete-adr-template
Provenance: code

Every bundled ADR generator and scaffold SHALL generate one `## Status`,
`## Context`, `## Decision`, `## Alternatives Considered`, and `## Consequences`
section.

#### Scenario: Generate or scaffold an ADR
- **WHEN** `new adr`, init, or seed writes an ADR
- **THEN** the generated document contains the five canonical sections exactly once

### Requirement: Warn on structurally unreviewable ADRs
ID: warn-unreviewable-adrs
Provenance: code

The `adr-structure` check MUST warn when an ADR is missing or duplicates a required
section, or when its Decision section is empty or contains only a known placeholder.

#### Scenario: Missing required section
- **WHEN** an ADR omits one of the canonical level-two sections
- **THEN** the check reports the missing section without inspecting lifecycle state

#### Scenario: Duplicate required section
- **WHEN** an ADR repeats one of the canonical level-two sections
- **THEN** the check reports the duplicate at the second heading

#### Scenario: Placeholder decision
- **WHEN** an ADR Decision section is empty or contains only a known placeholder
- **THEN** the check warns that the decision is not yet reviewable

## Tasks

- `T1` Implement and register the ADR structure check with focused fixture coverage. (req: warn-unreviewable-adrs)
- `T2` Expand the ADR generator template and test the canonical section set. (req: complete-adr-template)
- `T3` Document and dogfood the review-quality check. (component: checks)
- `T4` Document the complete generated ADR scaffold. (component: new-list-regen)
- `T5` Keep bundled init and seed ADRs warning-free under the configured profile. (component: seed)

## Drawbacks

- Draft ADRs with an empty Decision receive a warning while work is still in
  progress. That is intentional queue signal, but projects with many early drafts
  may choose not to configure the soft check yet.
- A structurally complete ADR can still contain a poor decision. Deterministic shape
  is not semantic review.
- Required sections add a small amount of authoring weight, largely absorbed by the
  generator.

## Alternatives

- **Use ADR prose as lifecycle truth.** Rejected: structured RFC metadata and graph
  links are a safer, independently validated authority.
- **Ship as a hard check immediately.** Rejected: existing repositories need a soft
  migration path, consistent with the warning policy.
- **Check section presence only.** Rejected: duplicate headings and a blank Decision
  are deterministic structural failures that presence alone misses.
- **Require `implements:` and `supersedes:` on every ADR.** Rejected: empty fields add
  no signal, and lifecycle relationships should be present only when they exist.
- **Build a generic required-sections engine for every doc kind.** Rejected: the ADR
  contract is small and specific; a generic configuration surface adds complexity
  before another document kind needs it.

## Resolution

Implemented with the complete ADR scaffold, the soft `adr-structure` check, focused
fixture coverage, and the repository ADR migration. The lifecycle boundary is
recorded by
[`ADR-0017`](../../50-decisions/0017-standardize-adr-structure.md): ADR prose remains
human-readable decision evidence, while RFC state stays in structured lifecycle
metadata.
