---
id: surface-rules-and-language-profiles-are-data
title: Surface rules and language profiles are data
status: stable
describes: []
summary: Code surfaces come from built-in framework packs and project rules that share one record, checks read a kind's capabilities rather than its name, and a language profile is the one list of its language's files.
governs:
  - src/irminsul/inventory/**
  - src/irminsul/surface.py
  - src/irminsul/languages/**
  - src/irminsul/checks/dependency_check.py#IMPORT_LANGUAGE
  - src/irminsul/config.py#_with_surface_rules
  - surface.rules
  - frameworks
  - languages.enabled
---

# Surface rules and language profiles are data

## Status

Accepted, 2026-10-28.

## Context

Code surfaces, such as commands, options, routes, exports and environment variables, must be
read in every language an adopter uses. If checks branch on kind names, a new language means
editing checks; if every adopter writes regular expressions, the work lands on the people least
placed to do it. A fact written in several places disagrees with itself: what counts as a
TypeScript file was once written five times with five answers.

## Decision

- **Framework packs ship as data.** Built-in packs read Typer, FastAPI and a Python MCP server
  through syntax-tree extractors, and Click, argparse, Flask, cobra, clap, commander and Express
  through rules. Every pack is active unless `frameworks.enabled` narrows the set.
- **A pack's rule and a project's rule are one record.** A project declares
  `[[surface.rules]]` with a `kind`, a `globs` list, a `pattern`, an `identity` template, an
  optional `guard` and an optional `mention_pattern`, and the packs build their rules from the
  same record. `guard` is a regular expression searched across a whole file with `^` at every
  line, and a file it does not match is not read. A config with `checks.inventory_drift` fails
  to load naming `[[surface.rules]]`, and a rule written with `glob` is an unknown key.
- **Checks read capabilities, not kind names.** A kind resolves to its mention pattern and
  whether its identity is a command path, which `inventory-drift`, `code-references` and
  `list review` read. A command path's program names come from package manifests, and
  `frameworks.command_names` overrides them.
- **A language profile is the one list of its files.** Every extractor and pack reads
  `LanguageProfile.suffixes`; the TypeScript profile lists JavaScript's with its own,
  `.ts .tsx .mts .cts .js .jsx .mjs .cjs`. Profiles exist for Python, TypeScript, Go and Rust;
  a language without one, such as Ruby, is read by none, and a project needing one of its
  surfaces declares a `surface.rules` rule.
- **`markers` and `confirmed_by` drive `init`.** A profile lists the root files that show its
  language, such as `go.mod` or `Cargo.toml`, and detection and the code-or-no-code test read
  them. `package.json` belongs to every JavaScript project, so TypeScript also needs a
  `tsconfig.json` or a `.ts` file.
- **`import-deps` names its language** in `IMPORT_LANGUAGE`, in `checks/dependency_check.py`:
  Python. The reader is not a profile field, because a profile is data.

## Alternatives Considered

- **Configuration rules only.** Rejected: every non-Python adopter would write regex.
- **Detect frameworks at `init` and enable only those.** Rejected: a framework added later would
  silently yield nothing.
- **A parser per framework.** Rejected for now: a pack can gain an extractor later.
- **Rules kept under `checks.inventory_drift`, or both names accepted.** Rejected: four readers
  use them, and one setting gets one name.
- **A suffix set per extractor, or a Ruby profile.** Rejected: several lists to keep equal, and a
  profile also carries schema-leak patterns and test conventions nobody has written for Ruby.

## Consequences

- A cobra, clap, commander or Express project gets commands, options and routes with no
  configuration; regex packs miss names a syntax tree would infer, such as a Click command named
  only by its function.
- An `env-vars` inventory item that only a `.rb` file reads is `inventory-drift/item-not-found`.
- **Known limits.** The lift of a base's old table lives in `parse_snapshot` and goes once no
  base a run can meet predates the rename. `anchors`, `binding`, `ranked_tests`, `import-deps`
  and the `uniqueness` skip list still test Python's suffix themselves, where they parse Python
  or name its files.
