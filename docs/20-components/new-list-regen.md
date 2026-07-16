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
implements:
  - 0023-adr-template-structure
  - 0035-rfc-lifecycle-integrity-and-frozen-records
---

# New / List / Regen / Fix commands

Doc-author UX commands for creating, finding, regenerating, and remediating documentation atoms.

## `irminsul new {adr,component,rfc}`

Scaffolds a new doc atom from a Jinja template under `src/irminsul/new/templates/`. ADRs go to `docs/50-decisions/<NNNN>-<slug>.md` (auto-numbered from the highest existing prefix); components to `docs/20-components/<slug>.md`; RFCs to `docs/80-evolution/rfcs/<NNNN>-<slug>.md`. Every generated doc has valid frontmatter that immediately passes `FrontmatterCheck`.

The ADR scaffold emits one `## Status`, `## Context`, `## Decision`, `## Alternatives Considered`, and `## Consequences` section, with Status initialized to `Proposed.`. It leaves lifecycle relationship fields absent until a real relationship exists; RFC state is governed by structured lifecycle metadata rather than inferred from the ADR body.

The `component` kind accepts repeatable `--describes` and `--tests` options that populate the scaffolded frontmatter lists instead of leaving them empty, so a new component doc can claim its sources in one command. Values are stored repo-relative in POSIX form; a value that does not exist on disk prints a yellow warning but is still written, since the file may be about to be created. With `--from-surface`, the scaffolded body gains a `## Surface` section derived from the claimed paths at scaffold time (CLI commands, HTTP endpoints, env vars, TS exports — whichever extractors find anything); paths with nothing derivable get a note and no section.

## `irminsul list {orphans,stale,undocumented}`

Thin wrappers over existing checks: `orphans` delegates to `OrphansCheck`, `stale` to `StaleReaperCheck`, `undocumented` to `UniquenessCheck` (filtering to omission warnings), and `lifecycle` combines `DecisionUpdatesCheck` with `RfcLifecycleIntegrityCheck`. Output is plain text by default; `--format json` emits a JSON array of the same finding records [`irminsul check --format json`](checks.md) produces — including `data` and `fixable`/`fix_command`. That sharing is deliberate: `lifecycle` wraps checks that *do* implement fixes, so a separate serializer here would be the one findings surface that hides fixability from agents.

By default `undocumented` only reports files in covered directories — directories where at least one file is already claimed. The `--all` flag drops that heuristic and lists every source file with no doc claim, grouped by directory with per-directory counts, directories sorted by undocumented count descending; this is the brownfield on-ramp for repos with little or no existing source-ownership mapping. In JSON mode each `--all` entry carries the file `path` and its parent `dir`.

`list lifecycle --queue` also includes accepted implementation backlog entries,
missing RFC seals, seal violations, premature implementation evidence, and stable
live docs that still point at draft RFCs. Each category receives a deterministic
priority, action kind, and suggested next command.

Pre-lifecycle RFCs appear as `migrate` work with the direct command
`irminsul change migrate <id>`. They are deliberately not folded into the draft
or implementation queues: choosing their lifecycle state is a human decision,
while the queue's job is to keep that unresolved decision visible.

## `irminsul fix`

Applies deterministic remediations for fixable findings selected by `--profile`. The default profile is `configured`; `hard`, `configured`, and `all-available` use the same selection policy as `irminsul check`. A check opts in by exposing a `fixes(findings, graph)` method that returns `Fix` objects; each fix only ever remediates a finding the check actually emits ([RFC 0022](../80-evolution/rfcs/0022-universal-fix-coverage.md)). The covered checks are `supersession` (deprecation metadata), `decision-updates` (the inverse `implements:` back-link), `inventory-drift` (pruning a drifted item), `rfc-resolution` (aligning a resolved RFC's `status` and inserting a scaffolding section), `glossary-discipline` (linking the first use of a term), and `rfc-lifecycle-integrity` (adding a missing legacy seal with `--confirm`; it never re-seals changed history).

`--dry-run` prints the edits that would be applied without writing files; normal runs group fixes by path and write each file atomically through a temporary file plus rename. Fixes that modify or remove existing content or load-bearing metadata are tagged `requires_confirm` and are held back — listed but not written — unless `--confirm` is passed; only purely additive inverse pointers apply by default. `--check <name>` harvests fixes from a single active check for targeted runs. Edits go through the shared [frontmatter-edit](frontmatter.md) helpers so every rewrite re-emits keys in canonical order and is idempotent.

## `irminsul regen`

`regen` produces deterministic generated artifacts and nothing else — it never writes prose or infers intent from code. The single artifact is `agents-md`: it rewrites the generated section of the [`docs/AGENTS.md`](../AGENTS.md) manifest from the doc graph while preserving the curated Foundations and Protocol sections.

The exact, current subcommand list is derived from the Typer app, not restated here — run `irminsul surface cli`.

## Scope & Limitations

`list` subcommands are read-only — they report findings but do not modify any docs. `regen` generates deterministic artifacts only; it does not produce prose descriptions or infer intent from source code. `fix` applies deterministic, pre-coded remediations only.
