---
id: seed
title: Seed command
status: stable
depends_on:
  - config
  - init
  - new-list-regen
describes:
  - src/irminsul/seed/**
owns_tests:
  - tests/test_seed.py
---

# Seed command

`irminsul seed` captures a project's PIB statement — its **principle** (what must
stay true even if features change), **idea** (what to build first), and
**belief** (why the direction is worth pursuing) — plus its first user,
non-goals, and direction risks. It materializes that intent into the foundation
layer so agents expand a stated direction instead of scaffold placeholders.

Seed writes four artifacts: the foundation principles doc, the architecture
overview doc, an anchoring ADR under `docs/decisions/` titled from the user's
idea, and an anchoring RFC (`initial-direction`) under
`docs/rfcs/`. The RFC records the original direction so later drift
can be compared against it explicitly, and it gives the rfcs layer a
non-empty starting point. Seed also links the anchoring ADR and RFC from the INDEX
beside each one when that INDEX exists (idempotently), so the
RFC is reachable from day one.

The anchoring ADR uses the canonical Status, Context, Decision, Alternatives
Considered, and Consequences sections. This keeps a freshly initialized and seeded
repository free of `adr-structure` findings, which the default `checks.enabled`
list includes.

Input arrives three ways: interactive prompts (the default), individual flags
(`--principle`, `--idea`, `--belief`, `--first-user`, `--non-goals`,
`--direction-risks`) together with `--no-interactive`, or a `--json` file. Without
`--no-interactive` the flags are ignored and seed prompts. The non-interactive forms
never invent missing intent — a missing required field is an error.

Seed is idempotent. While the foundation docs still contain known scaffold
placeholder phrases it writes freely. Once they have been edited away from
scaffold defaults it refuses to overwrite unless `--reseed` is passed; `--merge`
appends a new dated seed pass to the principles doc instead of replacing it. A
`--reseed` refreshes the foundation docs but does not re-anchor an
already-anchored project, so the ADR and RFC are created only on the first seed.

The interactive paths of [`irminsul init`](init.md) that scaffold a brand-new
project — `--fresh`, `--topology siblings`, and the no-code menu — offer to run
seed inline once scaffolding completes. That prompt appears on the interactive
path only — `init --no-interactive` gains no prompts and stays scriptable — and
`irminsul seed` remains the standalone command for capturing or redoing the seed
later.

The scaffold placeholder phrase set lives in `src/irminsul/init/placeholders.py`
alongside the scaffolds; both `seed` and the `foundation-readiness`
[check](checks.md) read it, so a fresh scaffold and its detection stay in sync.

## Scope & Limitations

Seed structures the user's belief; it cannot judge whether the belief is good —
that remains a human judgment. It does not scaffold application code, and it does
not run any checks itself.
