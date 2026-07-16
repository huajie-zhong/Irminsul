---
id: 0040-retired-reference-audit
title: "Detect references to retired commands and concepts"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
affects:
  - frontmatter
  - checks
---

# RFC 0040: Detect references to retired commands and concepts

## Summary

Let stable ADRs declare typed retirement tombstones, then warn when current
repository guidance still presents a removed CLI command or retired concept.
The declaration preserves provenance and replacement guidance; deterministic
matching keeps the audit local, explainable, and useful to agents.

## Motivation

Surface derivation proves what exists now, but it cannot explain whether a name
that disappeared was intentionally retired, renamed, or accidentally omitted.
Git history can show deletion without preserving the decision or replacement.
As a result, a stable component doc, README, glossary entry, or code example can
keep teaching a command or concept that the repository deliberately removed.

Retirement is a lifecycle fact. Its durable owner should be the accepted ADR
that made the decision, not an inferred negative inventory or a project-wide
list with no rationale.

## Requirements

### Requirement: Declare retirement tombstones
ID: declare-retirement-tombstones
Provenance: code

Frontmatter MUST support `retires` entries with a stable id, a typed kind
(`cli-command` or `concept`), one or more exact match phrases, and actionable
guidance. CLI entries MUST also name the extractor's canonical
`surface_identity`. Only stable ADR declarations are authoritative.

#### Scenario: Stable ADR declares a retirement
- **WHEN** a stable ADR carries a valid `retires` entry
- **THEN** its match phrases become active tombstones with the ADR as provenance

#### Scenario: Declaration has no authoritative owner
- **WHEN** a non-ADR or non-stable doc carries `retires`
- **THEN** the check reports that the declaration is inactive instead of silently using it

#### Scenario: Retired command is live again
- **WHEN** a CLI tombstone's `surface_identity` exists in the current derived CLI surface
- **THEN** the check reports a retirement contradiction on the ADR and does not flag current docs for that tombstone

### Requirement: Audit current guidance
ID: audit-current-guidance
Provenance: code

The check MUST scan stable non-historical doc atoms and current top-level
README, glossary, and contributor guidance. It MUST exclude ADR and RFC bodies,
deprecated or removed atoms, and generated navigation manifests.

#### Scenario: Removed command remains in an example
- **WHEN** current guidance contains a declared CLI command, including inside a fenced example
- **THEN** one warning identifies the phrase, declaring ADR, and replacement guidance

#### Scenario: Retired concept remains in prose
- **WHEN** current guidance contains a declared concept using case-insensitive token-boundary matching
- **THEN** one warning identifies the retired concept and its provenance

#### Scenario: Historical records contain the phrase
- **WHEN** the phrase occurs in an ADR, RFC, deprecated atom, or removed atom
- **THEN** no current-guidance finding is emitted

### Requirement: Permit explicit historical citations
ID: permit-historical-citations
Provenance: code

A current doc MAY mention a retired phrase without warning only when the exact
visible phrase is a Markdown link to the ADR that owns its tombstone.

#### Scenario: Exact phrase links its decision
- **WHEN** the exact retired phrase is linked to its declaring ADR
- **THEN** the mention is treated as an explicit historical citation

#### Scenario: Nearby or unrelated link
- **WHEN** the ADR is linked elsewhere or different link text is used
- **THEN** the retired phrase still produces a warning

### Requirement: Keep matching deterministic
ID: keep-retirement-matching-deterministic
Provenance: code

CLI command matching MUST be case-sensitive, whitespace-normalized, and
token-bounded. Concept matching MUST be case-insensitive, whitespace-normalized,
and token-bounded. Link destinations, reference definitions, URLs, and HTML
comments MUST NOT count as visible mentions.

#### Scenario: Phrase appears only in a destination
- **WHEN** a retired phrase occurs only inside a URL or Markdown link destination
- **THEN** the check emits no finding

#### Scenario: Two ADRs claim the same phrase
- **WHEN** multiple active tombstones normalize to the same kind and phrase
- **THEN** the check reports ambiguous retirement provenance deterministically

## Detailed Design

`DocFrontmatter.retires` contains validated `RetirementEntry` records. The soft
deterministic `retired-references` check builds a registry only from stable ADR
nodes, reports inactive and conflicting declarations, and scans current guidance
line by line so findings carry usable file locations. Before activating CLI
tombstones, it derives the current static CLI surface; a live identity produces a
contradiction finding and disables that tombstone for the run.

Inline and reference-style Markdown links retain their visible labels while
their destinations are masked. HTML comments, reference definitions, and bare
URLs are masked. Fenced code remains visible because obsolete examples are one
of the highest-risk failure modes. An exact link label resolving to the owning
ADR is recorded as the sole historical-citation exception.

V1 does not infer removals from Git because absence does not encode intent,
replacement, or ownership. Current CLI derivation can disprove a retirement but
cannot establish one. A retirement becomes auditable only when a human-approved
ADR records it.

## Tasks

- `T1` Add typed retirement entries to the frontmatter contract. (component: frontmatter)
- `T2` Build the ADR-owned retirement registry and deterministic matcher. (component: checks)
- `T3` Scan stable and top-level current guidance with precise findings. (req: audit-current-guidance)
- `T4` Prove historical citations and false-positive masks. (req: permit-historical-citations)
- `T5` Add retirement declarations for Irminsul's retired render and reference-layer surfaces. (component: checks)
- `T6` Document the declaration and audit contract. (component: frontmatter)

## Drawbacks

- Retirements made before this field exists need a small ADR metadata backfill.
- Exact phrases favor predictable behavior over fuzzy recall and require aliases
  to be listed deliberately.
- A warning cannot decide whether prose is semantically misleading; it requires
  either removal, replacement, or an explicit provenance link.

## Alternatives

- Diff the live CLI against old Git revisions. Rejected because deletion alone
  cannot distinguish retirement, rename, and accidental loss or provide durable
  replacement guidance.
- Put retired terms in `irminsul.toml`. Rejected because configuration would own
  a lifecycle decision without its rationale or approval record.
- Reuse `terminology-overload`. Rejected because ambiguity and retirement have
  different ownership, matching, exemptions, and remediation semantics.

## Unresolved Questions

- Whether future release tooling should require a retirement tombstone whenever
  a watched public surface removes an item belongs to a later integration RFC.
