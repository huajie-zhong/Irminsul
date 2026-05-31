---
id: 0011-derive-dont-materialize
title: "ADR-0011: Derive, don't materialize"
audience: adr
tier: 2
status: stable
describes: []
summary: Retire committed code-derived reference surfaces; derive on demand and govern the non-derivable.
supersedes:
  - 0003-generated-code-reference-surfaces
---

# ADR-0011: Derive, don't materialize

## Status

Accepted, 2026-05-30. Resolves [`0020-inventory-drift`](../80-evolution/rfcs/0020-inventory-drift.md). Supersedes [`ADR-0003`](0003-generated-code-reference-surfaces.md).

## Context

ADR-0003 made *committed generated* docs the canonical home for code-derived facts (the CLI command tree, frontmatter fields, the check registries), verified by `schema-doc-drift`, `cli-doc-drift`, and `check-surface-drift`. Practice showed the committed artifact is a **cache**: it goes stale, and a large share of irminsul's machinery existed only to police that staleness. The motivating incident for RFC-0020 — a component doc that hand-listed the `regen` subcommands and rotted when `regen agents-md` landed — was not a missing diff but a doc hand-copying a derivable fact.

## Decision

Adopt **derive, don't materialize** as a foundation principle: a fact reconstructable from code is never committed as a doc artifact; it is derived on demand. Concretely:

- Add a static extractor package and `irminsul surface <kind>` to derive a surface (commands, endpoints, exports, env vars) at call time, persisting nothing.
- Retire the committed reference surfaces and their drift checks; deprecate `regen docs-surfaces`. (Render-time mkdocstrings stubs stay — their content is pulled from live code at build.)
- Add `inventory:` frontmatter as *curated human intent* — a deliberate subset — checked by `inventory-drift` in the anti-lie direction only (a declared item must exist in code); there is no completeness pressure.
- Generalize `liar` into a boundary lint: prose that enumerates a derivable surface is told to derive or link.
- Relax `requires-env` and `import-deps` to intent-only, dropping their completeness directions.

## Alternatives Considered

- **Keep ADR-0003's committed surfaces + drift checks.** Rejected: the committed copy is a cache that drifts; policing it is machinery spent on a self-inflicted problem.
- **Inventory as a complete mirror (a second "undocumented surface" rule).** Rejected: that is the same materialization, relocated into frontmatter.
- **Require TypeDoc for TypeScript exports.** Rejected: a check must run in arbitrary CI without a node toolchain; a static export scan is used instead.

## Consequences

- Component docs hold only what code cannot express — rationale, invariants, and curated intent — and derive or link everything else.
- The remaining materialized artifact is the generated agent manifest (a cache of the doc graph). It is the agent entrypoint and needs an on-demand/render-time path designed first; it is a tracked follow-up, not part of this decision.
