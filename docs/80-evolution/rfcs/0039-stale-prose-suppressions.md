---
id: 0039-stale-prose-suppressions
title: "Detect stale prose file-reference suppressions"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
affects:
- checks
resolved_by: docs/50-decisions/0018-audit-stale-prose-suppressions.md
required_updates: []
---

# RFC 0039: Detect stale prose file-reference suppressions

## Summary

Audit explicit line and block suppressions used by `prose-file-reference`.
When a marker no longer hides an unlinked local Markdown filename, emit an
informational stale-suppression finding at the marker so obsolete exceptions do
not accumulate invisibly.

## Motivation

Irminsul already reports stale baseline fingerprints and stale watched-surface
`omit` entries. Inline prose suppressions are the remaining exception mechanism
that can outlive the condition it justified without any signal. That makes the
docs harder to trust and invites later text to be hidden accidentally by an old
block marker.

## Requirements

### Requirement: Audit line suppressions
ID: audit-line-suppressions
Provenance: code

A line suppression MUST be considered used only when the same non-fenced line,
with the marker removed, contains a local `.md` reference that the normal check
would report.

#### Scenario: Violation remains
- **WHEN** an unlinked local Markdown filename remains on the suppressed line
- **THEN** the marker is used and no stale-suppression finding is emitted

#### Scenario: Only linked references remain
- **WHEN** the line contains only valid Markdown links or no local filename
- **THEN** an informational stale-suppression finding points at the marker

### Requirement: Audit block suppressions
ID: audit-block-suppressions
Provenance: code

A matched block suppression MUST be considered used only when at least one
enclosed non-fenced line would independently produce the normal finding.

#### Scenario: Empty or clean block
- **WHEN** a matched block contains no suppressible violation
- **THEN** one stale-suppression finding points at its start marker

#### Scenario: Malformed block
- **WHEN** a start or end marker is unmatched
- **THEN** the existing hard malformed-marker finding remains authoritative and no duplicate stale finding is added

### Requirement: Keep stale suppressions visible
ID: keep-stale-suppressions-visible
Provenance: code

Stale-suppression findings MUST use info severity and structured
`problem: stale-suppression` data so baseline updates cannot suppress them and
agents can distinguish them from active prose violations.

#### Scenario: Baseline is updated
- **WHEN** a repository with a stale marker writes or applies a baseline
- **THEN** the informational stale-suppression finding remains in check output

## Detailed Design

The check uses one helper for its underlying question: whether a non-fenced line
contains an unlinked local Markdown filename after Markdown links and reference
definitions are masked. Normal findings and suppression-use tracking call the
same helper so their semantics cannot drift.

Line markers remove their containing HTML comment before the helper runs, which
prevents a filename inside `reason=` from making the suppression appear used.
Block markers track whether any enclosed line triggers the helper. A same-line
start/end pair has no enclosed content and is stale.

The finding uses `category: stale-suppression`, info severity, the marker's path
and line, and string-valued data identifying line or block scope. V1 does not
require a reason or auto-remove markers; pair-aware block editing is a separate,
riskier remediation contract.

## Tasks

- `T1` Share unlinked-reference detection between normal and suppression paths. (component: checks)
- `T2` Track used and stale line/block markers without changing malformed-marker errors. (component: checks)
- `T3` Prove informational findings survive baseline updates. (req: keep-stale-suppressions-visible)
- `T4` Document the suppression audit contract. (component: checks)

## Drawbacks

- Info findings add non-blocking output for repositories with old markers.
- V1 does not validate whether a suppression reason remains persuasive.
- Removal stays manual because block-pair edits are more dangerous than the
  deterministic detection implemented here.

## Alternatives

- Emit warnings. Rejected because warnings can be baselined, hiding the audit of
  the stale exception itself.
- Add a new global suppression registry. Rejected because it expands rather than
  repairs the existing exception surface.
- Remove markers automatically. Deferred until pair-aware fixes have their own
  safety and idempotence contract.

## Unresolved Questions

- Whether suppression reasons should become typed and required belongs to a
  later policy RFC.

## Resolution

Accepted by
[`ADR-0018`](../../50-decisions/0018-audit-stale-prose-suppressions.md): use the
same deterministic violation predicate to audit line and block exceptions,
report stale markers as non-baselineable information, and keep removal manual.
