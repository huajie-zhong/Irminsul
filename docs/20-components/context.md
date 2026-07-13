---
id: context
title: Agent context command
audience: explanation
tier: 3
status: stable
depends_on:
  - checks
  - config
  - docgraph
describes:
  - src/irminsul/context.py
tests:
  - tests/test_cli_context.py
---

# Agent context command

`irminsul context` returns task-specific navigation context from the current [DocGraph](docgraph.md). It is a runtime lookup, not a generated artifact.

The command supports exactly one input mode:

- `irminsul context <path>` for a source or doc path
- `irminsul context --topic <query>` for deterministic substring search over doc id, title, path, `describes`, and `tests`
- `irminsul context --changed` for staged, unstaged, and untracked git files
- `irminsul context --change <rfc-id>` as an alias for the [change lifecycle](change.md) status report, so an agent oriented around one RFC gets the same evidence view without switching command groups

Each result reports the owning doc, matching source claims, first declared entrypoint, tests, `depends_on`, docs that depend on it, relevant deterministic findings, and next command hints. `--profile configured|all-available` controls deterministic finding breadth.

## Scope & Limitations

Topic search is plain substring matching, not fuzzy search. `--changed` depends on `git status --porcelain` via the shared `irminsul.git.changes` helper (also used by the [change lifecycle](change.md) for its local diff baseline); outside a git worktree it reports the git error instead of guessing.
