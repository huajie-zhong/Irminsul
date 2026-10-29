---
id: surface
title: Surface extraction & on-demand derivation
status: stable
summary: Code surfaces derived on demand.
depends_on:
  - config
  - docgraph
  - languages
  - user-errors
describes:
  - src/irminsul/inventory/**
  - src/irminsul/surface.py
owns_tests:
  - tests/test_checks_inventory_drift.py
  - tests/test_cli_surface.py
  - tests/test_framework_packs.py
  - tests/test_inventory_extractors.py
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - check
      - surface
      - list review
---

# Surface extraction & on-demand derivation

This component is the engine behind *derive, don't materialize*. A code "surface" is a list reconstructable from source — the command set, the HTTP routes, the public exports, the environment variables a program reads, the long options a CLI accepts. Rather than committing a generated copy of such a list (a cache that rots), irminsul extracts it from code **on demand**.

## Why it is static-only

Extraction never imports or executes the target's code. `irminsul check` runs in arbitrary CI against repositories irminsul does not trust to import — doing so would run their import-time side effects and pull their dependencies into our process. So every extractor reads source as text or AST. The cost is a precision ceiling (dynamically registered routes, computed names, and re-exports through barrel files are invisible); the benefit is that extraction is safe everywhere.
<!-- anchor: src/irminsul/inventory/cli_typer.py#CliTyperExtractor.extract @sha256:372d40a855c5 -->


## Shape

Each surface *kind* maps to one small extractor that turns the source files into a list of identity strings. The identity is the only thing compared anywhere — a command path, a `METHOD /path`, a symbol name, a variable name — which keeps every consumer free of false positives from imperfect static parsing. Adding a kind or a language is a new extractor file plus a registry entry; the checks and the CLI do not change. A configurable regex extractor covers kinds and languages that have no dedicated plugin.

Run `irminsul surface <kind>` to see a surface, narrowed with `--source <glob>`; nothing is written. Every consumer starts from the same configured source inventory, so ignored or excluded generated and vendor files cannot silently re-enter through an extractor, and `SourceTree.surface` shares the extraction within a run.

## Packs and rules

Exports and environment variables are always on; framework packs add commands, long options, routes and MCP tools for the stacks they know, and `PACKS` lists them. Typer, FastAPI and MCP tools are read from the AST, and a Typer option declared once in a module-level `Annotated` alias counts for every parameter annotated with it. `command_options` reads one command's options by that same rule, which is how `code-references` knows whether a command declares an option, so an option written through an alias or by a default value is found on its command. The other packs are regular expressions guarded by an import or dependency marker, so the Click rules only read files that import Click, and they see what is written literally: a Click command named only by its function, or a cobra subcommand's parent path, is not recovered. Configuration rules under `[[surface.rules]]` add project-specific kinds in the same record the packs' own rules use ([`SurfaceRule`](config.md)).

A mention is only read as ours when the span it sits in is: a span opening with a program name that is not one of this project's own names describes that program's surface, and where no program name is known at all, an invocation is attributed to nobody. The names come from package manifests, or from `frameworks.command_names` when set.

## Scope & Limitations

Extraction is deliberately static and identity-only: it reports *what* exists, not attribute-level detail (an endpoint's parameters, an export's signature), and it cannot see surface elements that exist only at runtime. It derives; it does not persist — there is no generated artifact to commit or to drift. Judging whether a surface *should* exist, or whether prose about it is still true, is out of scope and left to the non-derivable-governance checks.

A source file that is not UTF-8, or Python that does not parse, contributes nothing to a surface and does not stop the run: `SourceReader` in `src/irminsul/inventory/base.py` is the one place that rule lives, and the graph's source tree is one, so the checks that read through it parse a file once per run. The skipped file is still reported as unclaimed by `uniqueness` when no doc describes it.
