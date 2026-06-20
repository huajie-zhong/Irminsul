---
id: orient
title: Agent orientation command
audience: explanation
tier: 3
status: stable
depends_on:
  - config
  - docgraph
describes:
  - src/irminsul/orient.py
tests:
  - tests/test_cli_orient.py
summary: The recommended first call for agents — repo structure, doc totals, entry docs, and the command vocabulary as one stable report.
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    complete: true
    items:
      - context
      - refs
      - surface
      - check
      - fix
      - list undocumented
    omit:
      - anchors
      - init
      - init-docs-only
      - list lifecycle
      - list orphans
      - list stale
      - new adr
      - new component
      - new rfc
      - orient
      - regen agents-md
      - seed
---

# Agent orientation command

`irminsul orient` is the single entry point for agents working in an Irminsul-managed repo: run it first, before reading or editing anything. It builds the [DocGraph](docgraph.md) once and reads [config](config.md) — no checks execute — so it is fast enough to run at the start of every session.

The report contains:

- the project name and docs root
- each top-level layer directory that contains docs, with its doc count
- doc totals, broken down by frontmatter `status`
- the entry docs that exist on disk under the docs root ([`AGENTS.md`](../AGENTS.md), [`README.md`](../README.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`GLOSSARY.md`](../GLOSSARY.md))
- the configured hard, soft deterministic, and soft LLM check names
- a curated command vocabulary: which command to run when, phrased for an agent working the edit-verify loop

## The JSON contract

Every agent-facing read command — `orient`, plus the existing `context`, `refs`, `surface`, `check`, `list`, and the `anchors` report — supports `--format json`. Every JSON report carries a top-level `version` field (currently `1`) so consumers can detect contract changes mechanically. `orient` is the recommended first call; its `commands` field teaches the rest of the vocabulary, so an agent that knows only `irminsul orient --format json` can discover the entire workflow loop from the output.

## Scope & Limitations

The report is a snapshot of structure, not health: it runs no checks and reports no findings — use the check pipeline for that. The command vocabulary is curated and static — the full command surface is derivable on demand instead (`irminsul surface cli`) — but its command *identities* are kept honest against that live surface by the `inventory:` block above, which opts into being a watched surface (`complete: true`): the `inventory-drift` check flags a renamed or removed taught command, a new command that is neither taught (`items`) nor explicitly excluded (`omit`), and a stale `omit` entry — all in `irminsul check` itself. The check is name-based, so it does not catch a command that keeps its name but changes behavior — a stale `when` description is left to human review (or an opt-in `fingerprints` pin). Entry docs are detected by filename convention only.
