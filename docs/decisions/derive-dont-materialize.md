---
id: derive-dont-materialize
title: Derive, don't materialize
status: stable
describes: []
summary: Facts reconstructable from code are derived on demand; docs keep curated intent, which watched and explained surfaces keep honest, and a review queue routes semantic checking to readers.
---

# Derive, don't materialize

## Status

Accepted, 2026-09-12.

## Context

A list that can be rebuilt from code — commands, options, endpoints, exports,
environment variables — goes stale the moment it is committed, whether as a generated
page or as hand-written prose. Yet docs still need to say which of those things matter
and why, and to stay true about them.

## Decision

- **Derive on demand.** Static extractors, which never import the target's code, back
  `irminsul surface <kind>`; nothing is written. The agent manifest is the only
  generated artifact.
- **Curate intent in `inventory:`.** A doc lists the subset of a surface it deliberately
  calls out, and `inventory-drift` reports listed identities the code no longer has.
- **Watch surfaces when completeness matters.** `complete: true` also reports live
  identities neither listed nor omitted; `fingerprints` pin each item's code shape;
  `explained_in: self|any` requires every live identity to be named in a code span of the
  docs, with `foreign` naming other tools' flags. Configuration keys, check names, and
  schema fields are watched through generic regex rules.
- **Guard the boundary.** `liar` reports prose that hand-lists a derivable surface. Names
  docs use in context, such as options and check names, count only when one list or
  table enumerates several of them.
- **Govern the MCP tool set as a watched surface,** for internal consistency rather than
  parity with the CLI.
- **Route semantic checking, don't perform it.** `irminsul list review` pairs each
  assertion that states current truth — in a live doc, a decision, or the glossary — with
  the code it names, using mechanical signals such as enforcement verbs and distinctive
  identities in plain prose, and orders the queue by whether that code moved after the
  doc; it never decides whether a sentence is true.
  Review items stay out of edit packets until the queue's signal-to-noise is known.

## Alternatives Considered

- **Generated reference pages verified in CI.** Rejected: they name everything, explain
  nothing, and drift between regenerations.
- **A two-surface parity check between MCP tools and CLI commands.** Rejected: the two
  surfaces differ by design.
- **Count plain-prose mentions as explanation.** Rejected: identifiers such as `reality`
  or `tags` collide with ordinary words.
- **Emit one finding per assertion.** Rejected: informational findings already number in
  the hundreds, and an ordered queue is workable where findings are not.

## Consequences

- Surfaces cannot drift in committed form, because nothing derivable is committed.
- Docs gain reference material they lacked; this repository found dead configuration by
  being made to explain it.
