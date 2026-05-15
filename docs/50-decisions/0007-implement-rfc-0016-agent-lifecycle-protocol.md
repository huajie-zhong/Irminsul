---
id: 0007-implement-rfc-0016-agent-lifecycle-protocol
title: "ADR-0007: Implement RFC-0016 agent lifecycle protocol"
audience: adr
tier: 2
status: stable
describes: []
summary: Add the canonical agent lifecycle protocol document and ship it via the init scaffold.
---

# ADR-0007: Implement RFC-0016 agent lifecycle protocol

## Status

Accepted, 2026-05-15. Resolves
[`0016-agent-lifecycle-protocol`](../80-evolution/rfcs/0016-agent-lifecycle-protocol.md).

## Context

[RFC-0016](../80-evolution/rfcs/0016-agent-lifecycle-protocol.md) proposed a
required work order for agents using Irminsul: read the manifest, run
`irminsul context`, create or update RFCs and ADRs for direction or behavior
changes, keep component and reference docs current, and run
`irminsul check --profile hard` before returning work. Until now the agent
navigation manifest at [`AGENTS.md`](../AGENTS.md) forward-referenced the
protocol without a canonical document, leaving the RFC itself as the de-facto
authority — fine while RFC 0013 was still landing, not durable now that all
dependencies (RFCs 0013 and 0014) are accepted.

## Decision

Implement RFC 0016:

- Add the canonical lifecycle document at
  [`docs/90-meta/agent-protocol.md`](../90-meta/agent-protocol.md). It is
  written in universal phrasing — the same body that scaffolds into new
  projects — and lists the ten-step work order verbatim from the RFC.
- Ship the same document as an init-scaffold template at
  `src/irminsul/init/scaffolds/docs/90-meta/agent-protocol.md.j2`, so every
  new project gets the protocol on day one. The existing scaffolder
  (`src/irminsul/init/command.py`) picks it up without code changes.
- Update the curated Protocol section of [`AGENTS.md`](../AGENTS.md) and the
  default Protocol section emitted by `irminsul regen agents-md` to deep-link
  straight at the new document.

No new check ships with this ADR. Enforcement of incomplete lifecycle
transitions is deferred per the RFC's own framing in
[§Drawbacks](../80-evolution/rfcs/0016-agent-lifecycle-protocol.md#drawbacks)
— later RFCs (notably [`0017-rfc-resolution-check`](../80-evolution/rfcs/0017-rfc-resolution-check.md))
add the mechanical checks.

## Alternatives Considered

- **Put the lifecycle guidance only in `CLAUDE.md` / agent-specific config.** <!-- irminsul:ignore prose-file-reference reason="CLAUDE.md is a repo-root agent instruction file, not a doc atom" -->
  Rejected by the RFC: Irminsul stays agent-neutral; the protocol belongs in
  the docs tree, not in any one tool's instruction file.
- **Keep the RFC itself as the canonical doc and skip the 90-meta document.**
  Rejected: the manifest's curated Protocol section needs a stable deep-link
  target inside the docs tree, and `80-evolution/rfcs/` is the wrong layer
  for an authoritative process document.
- **Expand the protocol doc with examples and worked walkthroughs per step.**
  Rejected for now: the verbatim ten-step list is the contract; rationale
  belongs in the RFC, examples belong in tutorials under `70-knowledge/` if
  ever needed.
- **Ship a hard `lifecycle-followed` check in this ADR.** Rejected per RFC
  drawbacks: the protocol needs advisory rollout before mechanical
  enforcement, and the targeted checks already proposed by RFCs 0017–0021
  cover the specific transitions worth detecting.

## Consequences

- Agents have a single canonical document for the lifecycle, deep-linked from
  the manifest; the "until RFC 0016 lands" caveat is removed from the curated
  Protocol section and from `regen agents-md`'s default.
- Every new project scaffolded by `irminsul init` ships with the protocol
  already populated under `docs/90-meta/`, so day-one agent work has the
  same contract as day-N.
- Protocol violations remain unenforced by checks for now; later RFCs and
  ADRs will add the mechanical signals.
- The protocol document is at tier 3 (living) so downstream projects can edit
  it to taste, the same way the curated Foundations and Protocol sections of
  [`AGENTS.md`](../AGENTS.md) are editable.
