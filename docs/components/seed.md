---
id: seed
title: Seed command
status: stable
summary: Capture starting intent into the foundation docs.
depends_on:
  - config
  - file-writing
  - frontmatter
  - init
  - user-errors
describes:
  - src/irminsul/seed/**
owns_tests:
  - tests/test_seed.py
---

# Seed command

`irminsul seed` captures a project's PIB statement — its **principle** (what must stay true even if features change), **idea** (what to build first) and **belief** (why the direction is worth pursuing) — and materializes it into the foundation layer so agents expand a stated direction instead of scaffold placeholders.

It writes only two docs, the foundation principles and the architecture overview ([Init adopts in two layouts, and seed fills two docs](../decisions/init-adopts-in-two-layouts-and-seed-fills-two-docs.md)), each rendered from the scaffold `irminsul init` writes it from with the answers in place of the marked prompts, so one template per doc serves both commands.

Input arrives from prompts, or from `--principle`, `--idea`, `--belief`, `--first-user`, `--non-goals` and `--direction-risks` with `--no-interactive`, where a missing required field is an error and never invented intent. `--reseed` overwrites an authored doc and `--merge` appends a dated pass instead.

The scaffold writes `<!-- irminsul:placeholder -->` beside each prompt, and `placeholder_lines()` in `src/irminsul/init/placeholders.py` reads which lines a marker covers for both `seed` and the `foundation-readiness` [check](checks.md). No list of the prompts' words exists, so rewording a prompt cannot hide it from either ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)).

## Scope & Limitations

Seed structures the user's belief; it cannot judge whether the belief is good — that remains a human judgment. It does not scaffold application code, and it does not run any checks itself.
