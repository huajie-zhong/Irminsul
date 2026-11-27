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
- **Checks read capabilities, not kind names.** A kind resolves to its mention pattern,
  whether its identity is a command path, and whether its identity is the name of a
  definition, as an export's is, which `inventory-drift`, `code-references` and `list review`
  read. A command path's program names come from package manifests, and
  `frameworks.command_names` overrides them.
- **A language profile is the one list of its files.** Every extractor and pack reads
  `LanguageProfile.suffixes`; the TypeScript profile lists JavaScript's with its own,
  `.ts .tsx .mts .cts .js .jsx .mjs .cjs`. A profile also holds the pattern that reads an
  environment variable in those files, which the `env-vars` surface matches, so that
  extractor names no language. Profiles exist for Python, TypeScript, Go and Rust;
  a language without one, such as Ruby, is read by none, and a project needing one of its
  surfaces declares a `surface.rules` rule.
- **`markers` and `confirmed_by` drive `init`.** A profile lists the root files that show its
  language, such as `go.mod` or `Cargo.toml`, and detection and the code-or-no-code test read
  them. `package.json` belongs to every JavaScript project, so TypeScript also needs a
  `tsconfig.json` or a `.ts` file.
- **A profile names its language's reader, which is code.** `LanguageProfile.reader` is a name
  that `READERS` in `src/irminsul/languages/__init__.py` maps to the reader, and
  `suffix_readers` names the dialect that reads a suffix, so the profile stays data. For a
  file's text a reader answers what it defines and on which lines, what it imports and which
  repository files an import may load, what a definition's body refers to, the canonical text
  a pin hashes, and which definitions are tests. A feature that reads code asks the reader of
  the file's language and names no language.
- **Python is read by its own parser, and TypeScript, JavaScript, Go and Rust through
  tree-sitter.** tree-sitter is a required dependency, with its runtime and each grammar
  pinned to one exact version. One reader serves those languages, with a query file each that
  says what a definition, an import and a test look like in the grammar, and a module each
  for what a query cannot say. JavaScript is read through the TSX dialect of TypeScript's
  grammar, which a measurement on 6,792 JavaScript files chose over a grammar of its own. A
  language is added by its profile, its grammar and its query file, with no change to a
  check.
- **A file its grammar cannot read whole still answers what parsed.** The grammars lag their
  languages, so a definition or an import whose own node holds no syntax error is answered,
  and the reading says the rest is unknown. Python stays all or nothing.
- **A missing import denies a dependency only where every import is placed.** A reading says
  whether every import of its file that stays in the repository is placed. A Python file's
  is, and a Go file's under a `go.mod`, when the file parses whole. A TypeScript or a
  Rust file's never is, since a
  path alias, a workspace package or another crate may stand between two files. `import-deps`
  reports a `depends_on` no import backs only when the two docs own code of a language in
  common and every file the depending doc owns of each such language has its imports placed.
  The test ranking and the `new-dependency` pass report only imports they found, so they read
  every language.

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
  files itself, as the source walk, the program names and the launchers each still name a
  language's files and tools themselves.
- An exact pin on tree-sitter and its grammars conflicts with another tool in the same
  environment that needs another version of them, and where no wheel exists, installing
  Irminsul compiles C code.
- A dependency that only a TypeScript path alias or a Rust path into another crate carries is
  neither denied nor seen, and one between two components of different languages is not
  judged. Nor is one between two components that each own a file of the same one of those
  languages beside their Python, TypeScript and JavaScript counting as one, which was judged
  through the Python alone before those files were read.

## Changes

- 2026-11-27: Accepted [Each language reads its code through one interface](../rfcs/each-language-reads-its-code-through-one-interface.md):
  a profile stays data and names its language's reader, which is code; Python's reader is its
  own parser and TypeScript's, Go's and Rust's are tree-sitter, a required dependency; and
  `import-deps` reads every language whose reader answers imports.
- 2026-11-27: The interface and Python's reader are implemented and stated in the Decision: a
  profile names its reader, and anchor pins, the definitions and tests `anchors --suggest`
  offers, the pairing of a code span with a function, the test ranking and both import checks
  read through it, so `IMPORT_LANGUAGE` is gone. No pin of code this left unchanged moved. The
  tree-sitter readers are not built yet and their rule joins the Decision when they are.
- 2026-11-27: The tree-sitter readers are implemented and stated in the Decision, with three
  answers the owner gave that day while they were built. A file with a syntax error to its
  grammar answers what parsed around it, where the RFC had it answer nothing: one Vitest
  idiom made 93 of 1,924 project files fail whole. `import-deps` judges a missing import only
  between docs whose common languages all have every import placed, which is Python and Go,
  where the RFC had it read every language that answers imports. And JavaScript is read
  through the TSX dialect, the outcome of the measurement the RFC's third decision asked for.
  Whether every import is placed is asked of a file, not of a language: a Go file with no
  `go.mod` above it has no module to place its imports by, which the review of the change
  found reported as a missing dependency. A Go file that does not parse whole places none.
  A Python file that does not parse still answers yes, as `import-deps` took it before, and
  whether it should is a question the backlog keeps for the owner.
- 2026-11-27: The owner answered that question the same day: a Python file that does not
  parse places no import either, as a Go file does not, so `import-deps` no longer reports a
  `depends_on` of a doc that owns one. None of such a file's imports is read, and a missing
  one proved nothing.
- 2026-11-27: The pattern that reads an environment variable is a field of the language's
  profile, `env_var_pattern`, where the `env-vars` extractor held one pattern per language
  and joined them to the profiles by suffix. The surface prints what it printed.
