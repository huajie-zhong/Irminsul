---
id: surface
title: Surface extraction & on-demand derivation
audience: explanation
tier: 3
status: stable
depends_on:
  - checks
  - config
describes:
  - src/irminsul/inventory/**
  - src/irminsul/surface.py
tests:
  - tests/test_inventory_extractors.py
  - tests/test_cli_surface.py
  - tests/test_checks_inventory_drift.py
---

# Surface extraction & on-demand derivation

This component is the engine behind *derive, don't materialize*. A code "surface"
is a list reconstructable from source — the command set, the HTTP routes, the public
exports, the environment variables a program reads. Rather than committing a
generated copy of such a list (a cache that rots), irminsul extracts it from code
**on demand**.

## Why it is static-only

Extraction never imports or executes the target's code. `irminsul check` runs in
arbitrary CI against repositories irminsul does not trust to import — doing so would
run their import-time side effects and pull their dependencies into our process. So
every extractor reads source as text or AST. The cost is a precision ceiling
(dynamically registered routes, computed names, and re-exports through barrel files
are invisible); the benefit is that extraction is safe everywhere.

## Shape

Each surface *kind* maps to one small extractor that turns the source files into a
list of identity strings. The identity is the only thing compared anywhere — a
command path, a `METHOD /path`, a symbol name, a variable name — which keeps every
consumer free of false positives from imperfect static parsing. Adding a kind or a
language is a new extractor file plus a registry entry; the checks and the CLI do
not change. A configurable regex extractor covers kinds and languages that have no
dedicated plugin.

Three consumers share this one engine: the `irminsul surface` query (aggregate the
live surface for a human or agent), the inventory-drift check (verify a doc's
curated subset still exists), and the boundary lint (catch a doc hand-copying a
surface). Run `irminsul surface <kind>` to see a surface; nothing is written.

## Scope & Limitations

Extraction is deliberately static and identity-only: it reports *what* exists, not
attribute-level detail (an endpoint's parameters, an export's signature), and it
cannot see surface elements that exist only at runtime. It derives; it does not
persist — there is no generated artifact to commit or to drift. Judging whether a
surface *should* exist, or whether prose about it is still true, is out of scope and
left to the non-derivable-governance checks.
