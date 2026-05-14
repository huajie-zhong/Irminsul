---
id: new-list-regen
title: New / List / Regen / Fix commands
audience: explanation
tier: 3
status: stable
depends_on:
  - checks
  - cli
  - config
  - docgraph
  - frontmatter
describes:
  - src/irminsul/new/**
  - src/irminsul/listing/**
  - src/irminsul/regen/**
  - src/irminsul/fix.py
tests:
  - tests/test_cli_new.py
  - tests/test_cli_regen.py
  - tests/test_cli_list.py
  - tests/test_cli_fix.py
---

# New / List / Regen / Fix commands

Doc-author UX commands for creating, finding, regenerating, and remediating documentation atoms.

## `irminsul new {adr,component,rfc}`

Scaffolds a new doc atom from a Jinja template under `src/irminsul/new/templates/`. ADRs go to `docs/50-decisions/<NNNN>-<slug>.md` (auto-numbered from the highest existing prefix); components to `docs/20-components/<slug>.md`; RFCs to `docs/80-evolution/rfcs/<NNNN>-<slug>.md`. Every generated doc has valid frontmatter that immediately passes `FrontmatterCheck`.

## `irminsul list {orphans,stale,undocumented}`

Thin wrappers over existing soft checks: `orphans` delegates to `OrphansCheck`, `stale` to `StaleReaperCheck`, `undocumented` to `UniquenessCheck` (filtering to omission warnings). Output is plain text by default; `--format json` emits a JSON array.

## `irminsul fix`

Applies deterministic remediations for fixable findings selected by `--profile`. The default profile is `configured`; `hard`, `configured`, `advisory`, and `all-available` use the same selection policy as `irminsul check`, but LLM advisory checks are never used for file mutation. The first implementation target is `SupersessionCheck`: when a new doc lists an old doc in `supersedes:`, `fix` can set the old doc's `status: deprecated` and `superseded_by: <new-id>` frontmatter. `--dry-run` prints the edits that would be applied without writing files; normal runs group fixes by path and write updated files atomically.

## `irminsul regen {python,typescript,docs-surfaces,agents-md,all}`

For Python, walks `source_roots`, finds all non-private `.py` files, and writes a mkdocstrings stub (`:::<dotted.module>`) under `docs/40-reference/python/`. The `id` in each stub matches the filename stem per the frontmatter rule.

For TypeScript, `irminsul regen typescript` requires local TypeDoc (`node_modules/.bin/typedoc` or `npx --no-install typedoc`) and writes minimal reference stubs under `docs/40-reference/typescript/`, mirroring the source directory layout. Stub IDs are derived from the full relative module path with `-` separators so nested files keep unique IDs.

`irminsul regen docs-surfaces` writes generated references for code-derived documentation surfaces, such as CLI commands and check registries.

`irminsul regen agents-md` writes the [`docs/AGENTS.md`](../AGENTS.md) agent navigation manifest: a generated documentation-tree section delimited by markers, plus curated Foundations and Protocol sections. When the manifest already exists, only the marked generated section is rewritten, so curated edits survive.

`irminsul regen all` runs every configured generated artifact.

## Scope & Limitations

`list` subcommands are read-only — they report findings but do not modify any docs. `regen` generates deterministic artifacts only; it does not produce prose descriptions or infer intent from source code. `fix` applies deterministic, pre-coded remediations only — it does not use LLM-based judgment to mutate files.
