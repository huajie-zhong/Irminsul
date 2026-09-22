---
id: surface
title: Surface extraction & on-demand derivation
status: stable
depends_on:
  - checks
  - config
describes:
  - src/irminsul/inventory/**
  - src/irminsul/surface.py
owns_tests:
  - tests/test_checks_inventory_drift.py
  - tests/test_cli_surface.py
  - tests/test_framework_packs.py
  - tests/test_inventory_extractors.py
  - tests/test_inventory_fingerprint.py
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - check
      - surface
      - list review
---

# Surface extraction & on-demand derivation

This component is the engine behind *derive, don't materialize*. A code "surface"
is a list reconstructable from source — the command set, the HTTP routes, the public
exports, the environment variables a program reads, the long options a CLI accepts. Rather than committing a
generated copy of such a list (a cache that rots), irminsul extracts it from code
**on demand**.

## Why it is static-only

Extraction never imports or executes the target's code. `irminsul check` runs in
arbitrary CI against repositories irminsul does not trust to import — doing so would
run their import-time side effects and pull their dependencies into our process. So
every extractor reads source as text or AST. The cost is a precision ceiling
(dynamically registered routes, computed names, and re-exports through barrel files
are invisible); the benefit is that extraction is safe everywhere.
<!-- anchor: src/irminsul/inventory/cli_typer.py#CliTyperExtractor.extract @sha256:9852f65e8d29 -->


## Shape

Each surface *kind* maps to one small extractor that turns the source files into a
list of identity strings. The identity is the only thing compared anywhere — a
command path, a `METHOD /path`, a symbol name, a variable name — which keeps every
consumer free of false positives from imperfect static parsing. Adding a kind or a
language is a new extractor file plus a registry entry; the checks and the CLI do
not change. A configurable regex extractor covers kinds and languages that have no
dedicated plugin.

Several consumers share this one engine: the `irminsul surface` query and its MCP
tool (aggregate the live surface for a human or agent), the `inventory-drift` check
(verify a doc's curated subset still exists, or that the docs explain every identity),
the `liar` check (catch a doc hand-copying a surface), `retired-references` (notice a
retired command that has come back), and `irminsul list review` (resolve the code a
sentence names). Run `irminsul surface <kind>` to see a surface, narrowed with `--source <glob>`; nothing is written.
Every consumer starts from the same configured source inventory, so ignored or
explicitly excluded generated/vendor files cannot silently re-enter through a
surface extractor.

## Framework packs

Kinds come from three places. Exports and environment variables are always on; environment variables are read from Python, JavaScript and TypeScript, Go, Rust, and Ruby source, and a generic rule of kind `env-vars` adds another language.
Framework packs add commands (`cli`), long options (`cli-options`), routes (`http`),
and MCP tools (`mcp`) for the stacks they know: `typer`, `click`, `argparse`,
`fastapi`, `flask`, and `mcp-python` for Python; `cobra` for Go; `clap` for Rust; and
`commander` and `express` for JavaScript and TypeScript. Every pack is active unless
`frameworks.enabled` lists a narrower set. Packs that contribute the same kind merge
their identities, so a doc watches `cli-options` whatever framework declares them.

Typer, FastAPI, and MCP tools are read from the AST; the other packs are regular
expressions guarded by an import or dependency marker, so the Click rules only read
files that import Click. Regex packs see what is written literally: a Click command
named only by its function, or a cobra subcommand's parent path, is not recovered.

Configuration rules under `[[checks.inventory_drift.generic]]` add project-specific
kinds with the same shape: a `glob`, a `pattern`, and an `identity` template, where
`{1}` inserts the first capture group, `{1|upper}` upper-cases it, and `{2?GET}` falls
back to `GET` when the group is empty.

Each kind carries capabilities that checks read instead of branching on its name. A
mention pattern lets an explained inventory report something identity-shaped that the
code does not declare; `cli-options` uses `--[a-z][a-z0-9-]*`, and a rule can set
`mention_pattern`. A mention is only read as ours when the span it sits in is: a span
opening with a program name that is not one of this project's own names describes that
program's surface, and where no program name is known at all, an invocation is attributed
to nobody — `frameworks.command_names` supplies them when no package manifest does. A prose-named kind is one whose identities docs name in context, so
`liar` does not treat several of them in a paragraph as a hand-copied list;
`cli-options` and `mcp` are prose-named, and a rule can set `prose_named`. `cli` is a
command path, matched word by word after a program name, which `irminsul list review`
reads from `[project.scripts]`, the `package.json` `bin` field, or Cargo binaries unless
`frameworks.command_names` sets it.

## Scope & Limitations

Extraction is deliberately static and identity-only: it reports *what* exists, not
attribute-level detail (an endpoint's parameters, an export's signature), and it
cannot see surface elements that exist only at runtime. It derives; it does not
persist — there is no generated artifact to commit or to drift. Judging whether a
surface *should* exist, or whether prose about it is still true, is out of scope and
left to the non-derivable-governance checks.
