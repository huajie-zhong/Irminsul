---
id: seed
title: Seed command
audience: explanation
tier: 3
status: stable
depends_on:
  - config
  - init
  - new-list-regen
describes:
  - src/irminsul/seed/**
tests:
  - tests/test_seed.py
---

# Seed command

`irminsul seed` captures a project's PIB statement — its **principle** (what must
stay true even if features change), **idea** (what to build first), and
**belief** (why the direction is worth pursuing) — plus its first user,
non-goals, and direction risks. It materializes that intent into the foundation
layer so agents expand a stated direction instead of scaffold placeholders.

Seed writes four artifacts: the foundation principles doc, the architecture
overview doc, an anchoring ADR under `docs/50-decisions/` titled from the user's
idea, and an anchoring RFC (`0001-initial-direction`) under
`docs/80-evolution/rfcs/`. The RFC records the original direction so later drift
can be compared against it explicitly, and it gives the evolution layer a
non-empty starting point.

Input arrives three ways: interactive prompts (the default), individual flags
(`--principle`, `--idea`, `--belief`, `--first-user`, `--non-goals`,
`--direction-risks`), or a `--json` file. The non-interactive forms never invent
missing intent — a missing required field is an error.

Seed is idempotent. While the foundation docs still contain known scaffold
placeholder phrases it writes freely. Once they have been edited away from
scaffold defaults it refuses to overwrite unless `--reseed` is passed; `--merge`
appends a new dated seed pass to the principles doc instead of replacing it. A
`--reseed` refreshes the foundation docs but does not re-anchor an
already-anchored project, so the ADR and RFC are created only on the first seed.

The interactive fresh-start path of [`irminsul init`](init.md) offers to run
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
