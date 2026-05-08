---
id: checks
title: Checks
audience: explanation
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes:
  - src/irminsul/checks/**
---

# Checks

Five hard, deterministic checks ship in v0.1.0. Each consumes a [DocGraph](docgraph.md) and returns a list of `Finding` records with severity, message, and a path/line where applicable.

| Check | What it enforces | Severity |
|-------|------------------|----------|
| `frontmatter` | Required fields present, enums valid, id matches filename rule, no duplicate ids | error |
| `globs` | Every `describes` pattern resolves to ≥1 source file | error |
| `uniqueness` | Each source file claimed by exactly one most-specific doc; ties are silent duplication | error / warning |
| `links` | Internal markdown links resolve; external/anchor-only skipped | error |
| `schema-leak` | No type/schema definitions inside `docs/20-components/` (those belong in `40-reference/`) | error |

Checks are registered in `HARD_REGISTRY` keyed by name. The CLI resolves `config.checks.hard ∩ HARD_REGISTRY` to pick what runs; unknown names emit a one-time skip note (forward-compatible with Sprint 2's soft checks).

Soft-deterministic and LLM checks are deferred to Sprint 2.
