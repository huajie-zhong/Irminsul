---
id: new-list-regen
title: New / List / Regen commands
audience: explanation
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes:
  - src/irminsul/new/**
  - src/irminsul/listing/**
  - src/irminsul/regen/**
---

# New / List / Regen commands

Three doc-author UX commands added in v0.2.0.

## `irminsul new {adr,component,rfc}`

Scaffolds a new doc atom from a Jinja template under `src/irminsul/new/templates/`. ADRs go to `docs/50-decisions/<NNNN>-<slug>.md` (auto-numbered from the highest existing prefix); components to `docs/20-components/<slug>.md`; RFCs to `docs/80-evolution/rfcs/<NNNN>-<slug>.md`. Every generated doc has valid frontmatter that immediately passes `FrontmatterCheck`.

## `irminsul list {orphans,stale,undocumented}`

Thin wrappers over existing soft checks: `orphans` delegates to `OrphansCheck`, `stale` to `StaleReaperCheck`, `undocumented` to `UniquenessCheck` (filtering to omission warnings). Output is plain text by default; `--format json` emits a JSON array.

## `irminsul regen --language=python`

Walks `source_roots`, finds all non-private `.py` files, and writes a mkdocstrings stub (`:::<dotted.module>`) under `docs/40-reference/python/`. The `id` in each stub matches the filename stem per the frontmatter rule. TypeScript support is deferred to Sprint 3.
