---
id: cli
title: CLI
audience: explanation
tier: 3
status: stable
depends_on:
  - change
  - checks
  - config
  - context
  - docgraph
  - init
  - new-list-regen
  - refs
  - seed
describes:
  - src/irminsul/cli.py
  - src/irminsul/__init__.py
tests:
  - tests/test_cli.py
  - tests/test_cli_check.py
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    complete: true
    items:
      - init
      - check
      - context
      - status
    omit:
      - init-docs-only
      - seed
      - orient
      - refs
      - fix
      - surface
      - anchors
      - mcp
      - change status
      - change verify
      - change transition
      - change finalize
      - change impact
      - new adr
      - new component
      - new rfc
      - list orphans
      - list stale
      - list undocumented
      - list lifecycle
      - regen agents-md
---

# CLI

The Typer app that backs both the `irminsul` and `irm` console scripts. The exact command surface is derived on demand from the Typer app — run `irminsul surface cli`.

Common command paths:

- `irminsul init` — scaffold a new codebase. Delegates to [`init`](init.md).
- `irminsul check` — build the [DocGraph](docgraph.md) and run checks selected by `--profile`. Exits 1 on any error finding. `--diff <base>` adds [co-change](checks.md) enforcement: a warning for every owning doc whose claimed source files changed in `<base>...HEAD` without it.
- `irminsul context` — build the [DocGraph](docgraph.md) and delegate task-specific navigation lookup to [`context`](context.md).
- `irminsul status` — summarize document inventory, source ownership, and configured findings through the [`status`](status.md) report.

Co-change accepts two spellings, and they fail differently on purpose. `--diff <base>` is an explicit opt-in gate: an unresolvable base ref exits 2 rather than passing silently, because a gate that cannot compute its diff is a gate that never fires. `--base-ref`/`--head-ref` predate it and degrade gracefully: an unresolvable ref (a shallow CI clone that never fetched the base sha, a tarball checkout with no history) prints a yellow warning on stderr and the run continues, reporting the rest of the findings normally. An empty value for any of the three is a malformed invocation and exits 2 either way.

Findings print one per line, sorted by severity then path. Severity colors are red (error), yellow (warning), cyan (info). Paths are POSIX-normalized so output is stable across platforms.

`irminsul check --profile` accepts `hard`, `configured`, and `all-available`. `hard` runs configured hard checks, `configured` adds configured deterministic warning checks, and `all-available` runs every implemented deterministic check.

The CLI is intentionally thin: every subcommand resolves config, builds a graph, calls into a registry of work, and prints. Logic lives in the modules it dispatches to.
<!-- anchor: src/irminsul/cli.py#check @sha256:c78429e96b77 -->


## Scope & Limitations

The CLI contains no domain logic; every subcommand dispatches to a dedicated module. It does not communicate with external services. There is no persistent state between invocations — each call is fully independent.
