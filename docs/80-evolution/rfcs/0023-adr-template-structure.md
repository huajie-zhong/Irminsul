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

Standardize the ADR shape: required frontmatter fields, required body
sections, and a new hard check `adr-structure` that enforces the shape. This
closes the loop that RFC-0017 (`resolved_by` lifecycle) and RFC-0018
(`implements` required updates) silently depend on.

## Motivation

RFC-0017 promotes `resolved_by` to a first-class lifecycle field that must
point at an ADR with a back-link. RFC-0018 introduces `implements` on ADRs as
the source-of-truth direction for decision back-links. Both expectations
assume ADRs have a consistent shape. Today's reality:

- `src/irminsul/new/templates/adr.md.j2` is a barebones template.
- Existing ADRs under `docs/50-decisions/` (ADR-0001, ADR-0002) vary in
  structure.
- Nothing enforces required sections.

Lifecycle checks from RFC-0017 and RFC-0018 can pass on syntactically valid
but operationally empty ADRs. An accepted RFC could be `resolved_by` an ADR
that has no `## Decision` section, and nothing would notice.

## Detailed Design

### Required frontmatter

Add these fields to the ADR template and require them via the new check:

```yaml
implements: ["<rfc-id-or-empty-list>"]
supersedes: ["<adr-id-or-empty-list>"]
summary: "one-line decision summary"
```

- `implements` is the source-of-truth link to RFCs the ADR implements; the
  inverse is auto-derived (per RFC-0018). It is already a real, checked field
  (`decision_updates`).
- `supersedes` lists prior ADRs this one replaces, in keeping with the
  supersession check.
- `summary` is the one-line decision summary the existing ADRs already carry.

Empty lists are valid for ADRs that do not implement an RFC or supersede a
prior ADR. The decision date is **not** a separate frontmatter field: ADRs
record it in the `## Status` line ("Accepted, YYYY-MM-DD."), matching the
convention every existing ADR follows.

### Required body sections

Enforced by a new hard check `adr-structure`. The required set matches the
convention every current ADR (0001–0014) already follows, so no existing ADR
needs restructuring:

- `## Status` — the current state and its date, plus the resolved RFC link when
  applicable ("Accepted, 2026-05-30. Resolves …").
- `## Context` — the situation that prompted the decision, including the RFC
  link when applicable.
- `## Decision` — the concrete choice, written in active voice ("We will
  ..."). Avoid hedging.
- `## Alternatives Considered` — the options weighed and why they were rejected.
- `## Consequences` — positive, negative, and follow-on work. Follow-on work
  here is the natural seed for `required_updates:` per RFC-0018.

### Backward fit

The required sections were chosen to match what all 14 existing ADRs
(0001–0014) already use, so the migration is small: only ADR-0001 (which has
just a `## Status` line) needs the remaining sections backfilled, and any ADR
missing `implements`/`supersedes` gets the empty-list fields added. The new
check ships soft for one release before being promoted to hard, matching the
warning-policy rollout pattern from RFC-0008.

### Template update

`src/irminsul/new/templates/adr.md.j2` is rewritten to emit the required
sections and frontmatter fields. New ADRs created via `irminsul new adr` are
structurally compliant by default.

## Relationship to Existing RFCs

- Closes the loop RFC-0017 depends on: accepted RFCs link to ADRs, and ADRs
  carry the structure to make the link meaningful.
- Makes RFC-0018's `implements:` field required on ADRs that resolve an RFC.
- Reuses the supersession field convention.

## Drawbacks

Required sections add some authoring weight. The fixup migration for
existing ADRs is one-time. Beyond migration, the template handles new ADRs
automatically.

The check cannot prove that the `## Decision` section says anything useful;
it can only prove the section exists. Semantic quality remains a reviewer
judgment.

## Alternatives

- Keep ADR shape as convention without a check. Rejected because RFC-0017
  and RFC-0018 cannot rely on conventions alone.
- Move ADR shape rules into the existing `FrontmatterCheck`. Rejected
  because section-presence is a body-level rule and FrontmatterCheck stays
  focused on frontmatter.
- Use a generic "required sections" check across all doc kinds. Rejected
  because section requirements are kind-specific and a generic check would
  spread its config across many docs.

## Unresolved Questions

- Should the soft-to-hard promotion wait a fixed release count, or gate on the
  existing ADRs all passing first?
