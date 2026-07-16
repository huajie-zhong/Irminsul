---
id: 0035-rfc-lifecycle-integrity-and-frozen-records
title: "RFC lifecycle integrity and frozen implemented records"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: implemented
affects:
- change
- checks
- config
- frontmatter
- init
- new-list-regen
resolved_by: docs/50-decisions/0016-freeze-implemented-rfc-records.md
required_updates:
- path: docs/20-components/change.md
  reason: Finalization now seals the implemented RFC.
  kind: update
- path: docs/20-components/checks.md
  reason: Document lifecycle-integrity findings and enforcement.
  kind: update
- path: docs/20-components/frontmatter.md
  reason: Document the frozen_hash lifecycle field.
  kind: update
- path: docs/20-components/config.md
  reason: Register lifecycle integrity in the default hard-check surface.
  kind: update
- path: docs/20-components/init.md
  reason: Scaffold lifecycle integrity for newly initialized repositories.
  kind: update
- path: docs/20-components/new-list-regen.md
  reason: Include lifecycle drift in list and fix behavior.
  kind: update
frozen_hash: "sha256:0abcf7398b29ef031cddd735d5ee723768b35897f64a472570e467cef7468921"
---

# RFC 0035: RFC lifecycle integrity and frozen implemented records

## Summary

Make `rfc_state: implemented` a durable terminal record. Finalization writes a
SHA-256 content seal into the RFC, and a hard deterministic check rejects any
later edit. An extension to shipped behavior therefore starts as a new RFC rather
than silently rewriting the proposal that justified the old implementation.

The same check exposes lifecycle drift that previously left shipped RFCs marked
draft: explicit `implements:` evidence before finalization is an error, while a
stable live-spec document linking a draft RFC is a warning for review. The
lifecycle list includes both conditions and missing legacy seals.

## Motivation

RFCs 0027 and 0029 through 0034 were implemented and merged while their documents
still said `draft`. The existing lifecycle checks validated decisions and required
updates, but did not ask whether durable implementation evidence contradicted the
RFC state. `list lifecycle` only added accepted RFCs to its implementation backlog,
so draft-but-shipped work was invisible.

Once an RFC is correctly finalized, editing it creates a second ambiguity: the
document can describe behavior that was never part of the reviewed implementation.
Git history can recover an older version, but it does not make the current record's
immutability explicit or enforce it in every repository that adopts Irminsul.

## Requirements

### Requirement: Freeze implemented RFCs
ID: freeze-implemented-rfcs
Provenance: code

An implemented RFC MUST carry a deterministic full-file SHA-256 seal, and a
content change after sealing MUST fail the hard check.

#### Scenario: Frozen content changes
- **WHEN** any frontmatter or body content other than the seal value changes
- **THEN** `rfc-lifecycle-integrity` reports a hard error and directs the author to a new RFC

#### Scenario: Legacy implemented RFC lacks a seal
- **WHEN** an implemented RFC has no `frozen_hash`
- **THEN** the check reports a fixable migration warning rather than breaking adoption

### Requirement: Detect lifecycle state contradictions
ID: detect-lifecycle-contradictions
Provenance: code

Irminsul MUST reject explicit implementation evidence for a non-implemented RFC
and MUST surface stable live documentation that presents a draft RFC as shipped.

#### Scenario: Premature implementation backlink
- **WHEN** a document declares `implements:` for a draft or accepted RFC
- **THEN** `rfc-lifecycle-integrity` reports a hard error

#### Scenario: Stable live doc links a draft
- **WHEN** a stable live-spec document links a draft RFC
- **THEN** the check reports a warning to verify and repair the stale state

### Requirement: Seal during finalization
ID: seal-during-finalization
Provenance: code

`irminsul change finalize` MUST write the seal after the state and status edits,
and `irminsul list lifecycle` MUST include freeze and lifecycle-drift findings.

#### Scenario: Accepted RFC finalizes
- **WHEN** all existing finalization preconditions pass and the confirmed writes succeed
- **THEN** the RFC ends as stable, implemented, and sealed

#### Scenario: Lifecycle queue is requested
- **WHEN** a repository contains a missing seal or lifecycle contradiction
- **THEN** `irminsul list lifecycle --queue` returns a categorized next action

## Detailed Design

`DocFrontmatter.frozen_hash` accepts only `sha256:` followed by 64 lowercase hex
characters. The canonical hash input is the complete Markdown file with line
endings normalized to LF and the top-level `frozen_hash` scalar line removed.
Removing only that line avoids self-reference while ensuring every other metadata
and prose edit changes the digest.

The `rfc-lifecycle-integrity` hard check has mixed severities:

- an implemented RFC without a seal is a fixable warning for one migration window;
- a seal mismatch or a seal on a non-implemented RFC is an error;
- an `implements:` backlink to a non-implemented RFC is an error;
- a stable live document outside decision, evolution, and meta layers linking a
  draft RFC is a warning because a link is evidence for review, not proof of shipping.

`irminsul fix --check rfc-lifecycle-integrity --confirm` adds missing seals but
never updates a mismatched seal. Re-sealing changed history would bless the exact
failure the check is intended to prevent. The valid remediation is to restore the
record or propose a superseding/extension RFC.

## Tasks

- `T1` Add the frozen hash field and deterministic seal helper. (component: frontmatter)
- `T2` Add lifecycle-integrity findings, fixes, and hard-check registration. (component: checks)
- `T3` Seal RFCs as the final confirmed finalization edit. (req: seal-during-finalization)
- `T4` Include lifecycle-integrity findings in the lifecycle queue. (component: new-list-regen)
- `T5` Migrate shipped RFCs 0027 and 0029 through 0034 to implemented sealed records. (component: change)
- `T6` Add lifecycle integrity to the default hard-check configuration. (component: config)
- `T7` Add lifecycle integrity to newly scaffolded repository configs. (component: init)

## Drawbacks

- Even typo fixes to an implemented RFC require a new record or restoration of the
  frozen text. This is deliberate: the RFC is history, while live documentation is
  the place to correct the current explanation.
- A stable-doc link is only a warning and may identify intentional historical
  references. Making it an error would confuse suggestive evidence with proof.
- Exact-byte hashing makes formatters visible after normalization. Authors must run
  formatting before finalization.

## Alternatives

- **Rely on Git history.** Rejected because it detects no violation in CI and leaves
  the current record mutable.
- **Hash only the RFC body.** Rejected because lifecycle and resolution metadata are
  part of the historical record.
- **Automatically re-seal edits.** Rejected because it turns enforcement into a
  mechanism for silently accepting rewritten history.
- **Infer shipping from arbitrary code changes.** Rejected because code proximity is
  not implementation proof; only explicit backlinks are errors.

## Resolution

Accepted and implemented on 2026-07-15 by
[`ADR-0016`](../../50-decisions/0016-freeze-implemented-rfc-records.md). The same
decision records the lifecycle migration of RFCs 0022, 0027, and 0029 through
0034.
