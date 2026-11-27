---
id: surface-rules-and-language-profiles-are-data
title: Surface rules and language profiles are data
status: stable
describes: []
summary: Code surfaces come from built-in framework packs and project rules that share one record, checks read a kind's capabilities rather than its name, and a language profile is the one list of its language's files and names the reader that reads their code.
governs:
  - src/irminsul/inventory/**
  - src/irminsul/surface.py
  - src/irminsul/languages/**
  - "!src/irminsul/languages/python_reader.py#_canonical"
  - "!src/irminsul/languages/python_reader.py#_find_symbol"
  - "!src/irminsul/languages/python_reader.py#PythonReading.canonical"
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
- **A profile names its language's reader, which is code.** `LanguageProfile.reader` is a name
  that `READERS` in `src/irminsul/languages/__init__.py` maps to the reader, so the profile
  stays data. For a file's text a reader answers what it defines and on which lines, what it
  imports and which repository files an import may load, what a definition's body refers to,
  the canonical text a pin hashes, and which definitions are tests. A feature that reads code
  asks the reader of the file's language and names no language, so `import-deps` reads every
  language whose reader answers imports. Python's reader is its own parser, `ast`. TypeScript,
  Go and Rust are read through tree-sitter, a required dependency (accepted, not yet
  implemented), and until then Python is the one language with a reader.

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
  base a run can meet predates the rename. The `uniqueness` skip list still names Python's
  files itself, and the cheap test `ranked_tests` makes before it reads a test file's imports,
  whether the file mentions the module's name, knows a Python package's `__init__.py`.

## Changes

- 2026-11-27: Accepted [Each language reads its code through one interface](../rfcs/each-language-reads-its-code-through-one-interface.md):
  a profile stays data and names its language's reader, which is code; Python's reader is its
  own parser and TypeScript's, Go's and Rust's are tree-sitter, a required dependency; and
  `import-deps` reads every language whose reader answers imports.
- 2026-11-27: The interface and Python's reader are implemented and stated in the Decision: a
  profile names its reader, and anchor pins, the definitions and tests `anchors --suggest`
  offers, the pairing of a code span with a function, the test ranking and both import checks
  read through it, so `IMPORT_LANGUAGE` is gone. No Python pin moved. The tree-sitter readers
  are not built yet.
