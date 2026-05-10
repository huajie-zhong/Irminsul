---
id: 0001-adopt-irminsul
title: "ADR-0001: Adopt the Irminsul doc system on Irminsul itself"
audience: adr
tier: 2
status: stable
describes: []
---

# ADR-0001: Adopt the Irminsul doc system on Irminsul itself

## Status

Accepted, 2026-05-08.

## Context

Irminsul is a documentation-system tool. If the project's own docs don't pass `irminsul check --profile=hard`, the tool's claims about doc rot have no credibility. We need to dogfood from day one — before v0.1.0 ships.

## Decision

Adopt Irminsul as the canonical doc system for the Irminsul codebase itself. The CI workflow runs `irminsul check --profile=hard` on every PR; failures block merge.

The reference document moves from the repo root (`Irminsul-reference.md`) into `docs/90-meta/doc-system.md` so it's discoverable through the standard layer structure rather than as a special-cased top-level file.

## Alternatives considered

- **Wait until v0.1.0 ships.** Tempting but circular — we'd be asking adopters to trust a system we hadn't tested ourselves.
- **Keep the reference at repo root with a redirect.** Adds a special case the doc system explicitly forbids (`90-meta/` is the canonical home for docs about the doc system). No good reason to break our own rule.

## Consequences

- Every PR that touches `src/irminsul/` is gated by `irminsul check`.
- Component docs under `docs/20-components/` declare `describes:` claims that cover the source tree; uniqueness will catch any source file that gets added without doc updates.
- The release workflow (when triggered) builds the same docs with `irminsul render` for the project site.
- We must keep the dogfood honest: when a check produces noise on this repo, fix the check (or document the carve-out), don't suppress the finding.
