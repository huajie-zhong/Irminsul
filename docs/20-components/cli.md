---
id: cli
title: CLI
audience: explanation
tier: 3
status: stable
describes:
  - src/irminsul/cli.py
  - src/irminsul/__init__.py
tests:
  - tests/test_cli.py
  - tests/test_cli_check.py
---

# CLI

The Typer app that backs both the `irminsul` and `irm` console scripts. Three commands ship in v0.1.0:

- `irminsul init` — scaffold a new codebase. Delegates to [`init`](init.md).
- `irminsul check` — build the [DocGraph](docgraph.md) and run checks selected by `--profile`. Exits 1 on any error finding.
- `irminsul render` — build a static site via the [renderer](render.md).

Findings print one per line, sorted by severity then path. Severity colors are red (error), yellow (warning), cyan (info). Paths are POSIX-normalized so output is stable across platforms.

`irminsul check --profile` accepts `hard`, `configured`, `advisory`, and `all-available`. `hard` runs configured hard checks, `configured` adds configured deterministic warning checks, `advisory` also runs configured LLM checks, and `all-available` runs every implemented deterministic check.

The CLI is intentionally thin: every subcommand resolves config, builds a graph, calls into a registry of work, and prints. Logic lives in the modules it dispatches to.
