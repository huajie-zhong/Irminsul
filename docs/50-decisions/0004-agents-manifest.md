---
id: 0004-agents-manifest
title: "ADR-0004: Add the agent navigation manifest"
audience: adr
tier: 2
status: stable
describes: []
summary: Add an agent navigation manifest plus an opt-in hard check and a regen target.
---

# ADR-0004: Add the agent navigation manifest

## Status

Accepted, 2026-05-14. Resolves
[`0013-agents-manifest`](../80-evolution/rfcs/0013-agents-manifest.md).

## Context

New agents have no curated entry point into the documentation tree. The root agent
guidance file covers code-facing instructions and `irminsul context` answers per-task
questions, but neither is a map of `docs/`. RFC 0013 proposed a required agent navigation
manifest at the top of the docs tree with a generated documentation-tree section plus
curated Foundations and Protocol sections, backed by a hard `agents-manifest` check and an
`irminsul regen agents-md` target.

## Decision

Add [the agent navigation manifest](../AGENTS.md) as an exempt top-level docs file — like
the repo README, it is navigation rather than a doc atom, so it carries no frontmatter and
is validated by its own check instead of the doc graph. It has three sections: a generated
tree-by-layer table delimited by `agents-manifest:generated-start` / `-end` markers, a
curated Foundations digest (the Three Laws, the layered structure, the tier system), and a
curated Protocol pointer that deep-links to RFC 0016.

Ship `irminsul regen agents-md`, which scaffolds the full manifest when absent and
rewrites only the marked generated section when present, preserving curated content. Add a
hard `agents-manifest` check that errors when the manifest is missing, when its generated
section has drifted, or when a required heading is absent.

The check ships **opt-in**: it is registered in the hard registry and accepted in
`checks.hard`, and this repo enables it, but it is not in the default hard set. Making it a
default-on requirement for every consuming project is deferred so it does not break repos
that have no manifest yet.

## Alternatives Considered

- **A static agent index under `docs/90-meta/`.** Rejected: RFC 0011 already chose the
  task-scoped `irminsul context` command over a broad static index.
- **A pure-curated manifest.** Rejected: it rots as the documentation tree changes.
- **A pure-generated manifest.** Rejected: generated data alone loses the foundation
  framing agents need before editing docs.
- **A default-on hard check immediately.** Rejected for this decision: it would fail every
  repo on default config that lacks a manifest.

## Consequences

- Agents get a single curated map of `docs/`, kept honest by a hard drift check on this
  repo.
- Adding or moving any doc requires rerunning `irminsul regen agents-md`.
- Deferred to other RFCs: `irminsul fix` auto-regeneration of the manifest belongs to
  RFC 0022; the canonical lifecycle protocol document under `docs/90-meta/` belongs to
  RFC 0016 (the Protocol section deep-links to RFC 0016 until then); default-on rollout of
  the `agents-manifest` check for consuming projects is a later step.
