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

The `component` kind accepts repeatable `--describes` and `--tests` options that populate the scaffolded frontmatter lists instead of leaving them empty, so a new component doc can claim its sources in one command. Values are stored repo-relative in POSIX form; a value that does not exist on disk prints a yellow warning but is still written, since the file may be about to be created.

## `irminsul list {orphans,stale,undocumented}`

Thin wrappers over existing soft checks: `orphans` delegates to `OrphansCheck`, `stale` to `StaleReaperCheck`, `undocumented` to `UniquenessCheck` (filtering to omission warnings). Output is plain text by default; `--format json` emits a JSON array.

By default `undocumented` only reports files in covered directories — directories where at least one file is already claimed. The `--all` flag drops that heuristic and lists every source file with no doc claim, grouped by directory with per-directory counts, directories sorted by undocumented count descending; this is the brownfield on-ramp for repos with little or no existing coverage. In JSON mode each `--all` entry carries the file `path` and its parent `dir`.

## `irminsul fix`

Applies deterministic remediations for fixable findings selected by `--profile`. The default profile is `configured`; `hard`, `configured`, `advisory`, and `all-available` use the same selection policy as `irminsul check`, but LLM advisory checks are never used for file mutation. A check opts in by exposing a `fixes(findings, graph)` method that returns `Fix` objects; each fix only ever remediates a finding the check actually emits ([RFC 0022](../80-evolution/rfcs/0022-universal-fix-coverage.md)). The covered checks are `supersession` (deprecation metadata), `decision-updates` (the inverse `implements:` back-link), `inventory-drift` (pruning a drifted item), `rfc-resolution` (aligning a resolved RFC's `status` and inserting a scaffolding section), and `glossary-discipline` (linking the first use of a term).

`--dry-run` prints the edits that would be applied without writing files; normal runs group fixes by path and write each file atomically through a temporary file plus rename. Fixes that modify or remove existing content or load-bearing metadata are tagged `requires_confirm` and are held back — listed but not written — unless `--confirm` is passed; only purely additive inverse pointers apply by default. `--check <name>` harvests fixes from a single active check for targeted runs. Edits go through the shared [frontmatter-edit](frontmatter.md) helpers so every rewrite re-emits keys in canonical order and is idempotent.

## `irminsul regen`

`regen` produces deterministic generated artifacts and nothing else — it never writes prose or infers intent from code. The single artifact is `agents-md`: it rewrites the generated section of the [`docs/AGENTS.md`](../AGENTS.md) manifest from the doc graph while preserving the curated Foundations and Protocol sections.

The exact, current subcommand list is derived from the Typer app, not restated here — run `irminsul surface cli`.

## Scope & Limitations

`list` subcommands are read-only — they report findings but do not modify any docs. `regen` generates deterministic artifacts only; it does not produce prose descriptions or infer intent from source code. `fix` applies deterministic, pre-coded remediations only — it does not use LLM-based judgment to mutate files.
