---
id: 0023-adr-template-structure
title: ADR template and structured decision record
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0023: ADR template and structured decision record

## Summary

Standardize the ADR shape so the lifecycle checks that already lean on it have
something real to verify. Two parts: (1) rewrite the ADR template
(`src/irminsul/new/templates/adr.md.j2`) so new ADRs are structurally complete
by default, and (2) add a **soft deterministic** check `adr-structure` that
verifies every ADR carries the required body sections. The check ships soft (a
warning in `SOFT_REGISTRY`), matching every comparable lifecycle check;
promotion to a hard gate is deferred under the RFC-0008 warning policy and is
out of scope here.

## Motivation

RFC-0017 promotes `resolved_by` to a lifecycle field whose human-readable
meaning lives in the ADR's `## Status` line (the acceptance date and the
resolved-RFC link). RFC-0018 treats `implements:` on ADRs as the
source-of-truth decision back-link. Both assume ADRs share a shape. Today:

- The ADR template (`src/irminsul/new/templates/adr.md.j2`) is barebones:
  `## Context`, `## Decision`, `## Consequences` only — no `## Status`, no
  `## Alternatives Considered`.
- The decision docs under `docs/50-decisions/` vary. Only three sections
  (`## Context`, `## Decision`, `## Consequences`) appear in every ADR.
- Nothing enforces section presence, so an accepted RFC can be `resolved_by`
  an ADR that has no `## Decision` section and nothing notices.

## Detailed Design

### Required body sections

The new check `adr-structure` requires these sections on every doc with
`audience: adr`:

- `## Status` — the current state and its date, plus the resolved-RFC link
  when applicable ("Accepted, 2026-05-30. Resolves …"). This is the line
  RFC-0017's lifecycle reads.
- `## Context` — the situation that prompted the decision.
- `## Decision` — the concrete choice, in active voice.
- `## Alternatives Considered` — the options weighed and why they were rejected.
- `## Consequences` — positive, negative, and follow-on work; the natural seed
  for `required_updates:` per RFC-0018.

Heading matching is case-insensitive, so an existing `## Alternatives
considered` passes without an edit. The check scopes itself to `audience: adr`
and therefore ignores `docs/50-decisions/INDEX.md` (`audience: reference`).

### Frontmatter: validate-when-present, not required

`implements:` and `supersedes:` already exist in the canonical frontmatter
schema as optional lists and are validated when present — `implements:` by the
`decision-updates` check, `supersedes:` by `supersession`. This RFC does
**not** make them required. Two reasons: empty and absent are
indistinguishable after the schema applies its default, so a presence rule
would require re-parsing the raw frontmatter for no real signal; and requiring
them would add empty fields to every existing ADR for no behavioral gain. The
rewritten template emits `implements: []` / `supersedes: []` as scaffolding so
authors fill them in, but their absence is not a finding.

### Backward fit (the real survey)

The required-section set is **not** universally satisfied today, so the
migration is small but real, not zero. A survey of `docs/50-decisions/`:

- `## Context`, `## Decision`, `## Consequences` — present in every ADR.
- `## Status` — missing from ADR-0002, ADR-0006, ADR-0008, ADR-0009, and
  ADR-0010.
- `## Alternatives Considered` — missing from ADR-0006; ADR-0001 spells it
  lowercase (`## Alternatives considered`), which passes under
  case-insensitive matching but is normalized to the canonical casing for
  tidiness.

The implementing PR adds the missing `## Status` sections to those five ADRs
and the missing `## Alternatives Considered` to ADR-0006. Because the check
ships soft, this backfill does not gate `--profile=hard`; it is done so the
dogfooded repo is exemplary and `--profile=configured` stays clean.

### Template update

`src/irminsul/new/templates/adr.md.j2` is rewritten to emit `## Status`,
`## Context`, `## Decision`, `## Alternatives Considered`, and
`## Consequences`, plus `implements: []` / `supersedes: []` frontmatter
scaffolding. New ADRs created via `irminsul new adr` are structurally
compliant by default.

## Relationship to Existing RFCs

- Gives RFC-0017's `resolved_by` / `## Status` link and RFC-0018's
  `implements:` back-link a guaranteed place to live.
- Reuses the existing `supersedes` / `implements` fields rather than inventing
  new ones.
- Defers the heading-as-hard-gate to a later promotion under the RFC-0008
  warning policy.

## Drawbacks

Required sections add minor authoring weight, absorbed by the template for new
ADRs. The check proves a section exists, not that it says anything useful —
semantic quality remains a reviewer judgment.

## Alternatives

- **Ship as a hard check immediately.** Rejected: every comparable lifecycle
  check (`rfc-resolution`, `decision-updates`, `inventory-drift`) ships soft
  first, and `HARD_REGISTRY` is a deliberately small stable core. Soft-first
  matches the RFC-0008 rollout.
- **Require `implements:` / `supersedes:` presence.** Rejected: no signal over
  validate-when-present, and it churns every ADR (see above).
- **Keep ADR shape as convention without a check.** Rejected: RFC-0017 and
  RFC-0018 cannot lean on convention alone.
- **Fold section rules into `FrontmatterCheck`.** Rejected: section presence is
  a body-level rule and FrontmatterCheck stays focused on frontmatter.
- **A generic "required sections" check across all doc kinds.** Rejected:
  section requirements are kind-specific, and a generic check would spread its
  config across many docs.

## Status

- Proposed. Lands as one PR: the `adr-structure` soft check, the template
  rewrite, and the ADR backfill described above.
