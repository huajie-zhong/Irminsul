---
id: 0020-inventory-drift
title: Derive, don't materialize — surfaces, curated inventory, and the boundary lint
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
affects: [checks, surface]
resolved_by: docs/50-decisions/0011-derive-dont-materialize.md
required_updates: []
---

# RFC 0020: Derive, don't materialize

## Summary

Originally proposed as an `inventory` frontmatter field plus an `inventory-drift`
check that diffs a declared list against code. The interview reframed it: a list
reconstructable from code is a *derivation*, and a committed copy of a derivation —
whether a generated `.md` or a hand-declared "complete" list — is a cache that goes
stale. The accepted design **derives surfaces on demand**, keeps in docs only what
code cannot express, and adds a lint that enforces that boundary.

## Motivation

Component docs hand-copied code-derived facts (the `regen` subcommands listed in
`new-list-regen` prose) and rotted when the code changed (`regen agents-md` landed
with no update). The pre-existing drift checks (`cli-doc-drift`, `schema-doc-drift`,
`check-surface-drift`) only policed *committed generated* references — they could
not see hand-written prose, and they existed only because we had materialized a
cache in the first place.

## Detailed Design (as shipped)

**Static extractors** (`src/irminsul/inventory/`). One small extractor per surface
*kind* — `cli` (Typer, AST), `http` (FastAPI, AST), `exports` (TypeScript, static
scan, no node toolchain), `env-vars` (regex), plus a config-declared generic regex
fallback. Extraction is static only: `irminsul check` runs against untrusted repos
and must never import their code. Identity-only comparison (command path,
`METHOD /path`, symbol name, var name) keeps every consumer free of false positives
from imperfect parsing. A test pins the CLI extractor to Typer's live command
resolution for irminsul itself.

**On-demand derivation** (`irminsul surface <kind>`). Derives and aggregates a
surface from code at call time and persists nothing — the positive replacement for
committed reference docs.

**`inventory:` as curated intent.** A doc may declare a deliberately-chosen *subset*
of a surface (`kind` / optional `source` / `items`). The `inventory-drift` check
runs the anti-lie direction only: a declared item that no longer exists in code is
flagged. There is deliberately no completeness rule — that would be the same
materialization, relocated into frontmatter. Use `irminsul surface` for the full
surface.

**Boundary lint** (the generalized `liar` check). A doc whose prose enumerates a
derivable surface (≥3 identities of one kind, in invoked/exact form, in
explanation/reference docs not already declaring an `inventory` block) is told to
declare a curated inventory or link to the derivation. This is the principled
successor to the old "fields duplicated from a reference doc" check, now sourced
from the extractors rather than a committed generated doc.

**Retirements.** `cli-doc-drift`, `schema-doc-drift`, `check-surface-drift` and the
committed `docs/40-reference/{cli-commands,frontmatter-fields,check-registries}.md`
are removed; `regen docs-surfaces` is deprecated. `requires-env` and `import-deps`
are relaxed to their intent-only (anti-lie) directions. Render-time mkdocstrings
stubs stay — their content is pulled from live code at build.

The principle is recorded in the foundation docs ("Derive, don't materialize") and
the decision in ADR-0011.

## Resolution

Accepted and implemented; resolved by
[`ADR-0011`](../../50-decisions/0011-derive-dont-materialize.md), which also
supersedes ADR-0003 (the committed-generated-surfaces decision this reverses).

The two original Unresolved Questions are resolved by the reframe: `inventory.items`
is a flat list (grouped sub-lists are unnecessary for a curated subset), and HTTP
query parameters / request bodies stay out of scope — comparison is identity-only
(`METHOD /path`). The complementary RFC-0024 (anchored prose claims) adds the
deterministic intent-staleness backstop that the shift to category-2 content makes
necessary.
