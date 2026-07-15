---
id: 0023-adr-template-structure
title: ADR template and structured decision record
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
affects:
  - checks
  - new-list-regen
---

# RFC 0023: ADR template and structured decision record

## Summary

Standardize ADRs as reviewable decision records. New ADRs should contain `Status`,
`Context`, `Decision`, `Alternatives Considered`, and `Consequences`; a soft
deterministic `adr-structure` check should warn when an ADR omits a required section
or leaves its decision empty.

This proposal complements the RFC lifecycle but is not a hidden dependency of it.
Lifecycle truth comes from structured frontmatter, graph links, and the RFC's
resolution. ADR structure makes the human decision behind `resolved_by` consistent
and inspectable; it does not infer acceptance dates, implementation, or backlinks
from prose headings.

## Motivation

The original draft assumed lifecycle checks read an ADR's `## Status` line and used
`implements:` on ADRs as the authoritative reverse edge. The shipped lifecycle no
longer works that way: `rfc_state`, `resolved_by`, `required_updates`, and explicit
graph links are the deterministic contract, while finalization promotes implementation
evidence into owning component docs.

ADR quality is still uneven. The generator currently creates only `Context`,
`Decision`, and `Consequences`, and existing records vary. A `resolved_by` target can
therefore pass lifecycle checks while saying little about alternatives or even
carrying an empty decision. That is a reviewability gap, not lifecycle-state proof.

## Requirements

### Requirement: Complete generated ADR shape
ID: complete-adr-template
Provenance: code

`irminsul new adr` SHALL generate the five required sections in a stable order and
include useful prompts without inventing a decision.

#### Scenario: New ADR is scaffolded
- **WHEN** an author runs `irminsul new adr`
- **THEN** the generated record contains Status, Context, Decision, Alternatives Considered, and Consequences

### Requirement: Warn on unreviewable ADRs
ID: warn-unreviewable-adrs
Provenance: code

The `adr-structure` check MUST warn when an `audience: adr` document is missing a
required section, duplicates one, or has no substantive Decision content.

#### Scenario: ADR omits alternatives
- **WHEN** an ADR has no `## Alternatives Considered` section
- **THEN** the check reports a warning naming that section

#### Scenario: ADR has an empty decision
- **WHEN** the Decision section contains only whitespace or a scaffold prompt
- **THEN** the check reports a warning that the decision is not reviewable

## Detailed Design

The ADR template becomes:

```markdown
## Status

Proposed.

## Context

## Decision

## Alternatives Considered

## Consequences
```

`adr-structure` applies only to parsed atoms whose `audience` is `adr`. It uses the
DocGraph heading index so fenced examples do not count as sections. The required
headings are exact H2 names; extra sections are allowed. Presence and uniqueness are
structural checks. For `Decision`, the check also rejects empty content and known
scaffold placeholder text, because an empty heading provides no review value.

The check remains soft under the RFC-0008 warning policy. Existing ADRs are not
rewritten automatically: alternatives and consequences require author judgment.
`irminsul fix` may eventually add missing empty headings, but it must not fabricate
their prose and is out of scope for this RFC.

The check does not parse a lifecycle state from `Status`, require an acceptance date,
or use ADR prose as a reverse implementation edge. Those responsibilities remain in
the frontmatter and lifecycle checks.

## Tasks

- `T1` Expand the ADR scaffold to the required section shape. (req: complete-adr-template)
- `T2` Add the soft deterministic adr-structure check. (req: warn-unreviewable-adrs)
- `T3` Add green and failing fixture ADRs, including an empty Decision. (component: checks)
- `T4` Review existing project ADRs and backfill prose manually where useful. (component: new-list-regen)

## Drawbacks

- Existing repositories receive warnings until older ADRs are reviewed.
- Heading consistency cannot determine whether a decision is wise or complete.
- A substantive-content heuristic must stay narrow to avoid pretending to judge prose.

## Alternatives

- **Keep only the current three sections.** Rejected because status and alternatives
  are recurring review questions that should not depend on author memory.
- **Make ADR structure a hard check immediately.** Rejected under the warning
  promotion policy; brownfield records need a migration period.
- **Derive RFC lifecycle from ADR prose.** Rejected because structured metadata and
  graph edges are less ambiguous and already implemented.
- **Auto-write missing ADR content.** Rejected because a deterministic tool cannot
  invent the reasoning behind a decision.

## Unresolved Questions

- Which placeholder phrases should count as an empty Decision across custom templates?
- Should a later RFC add a confirmed fixer that inserts only missing headings?
