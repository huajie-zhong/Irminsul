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
  - tests/test_context_unit.py
---

# Agent context command

`irminsul context` returns task-specific navigation context from the current [DocGraph](docgraph.md). It is a runtime lookup, not a generated artifact.

The command supports exactly one input mode:

- `irminsul context <path>` for a source or doc path
- `irminsul context --topic <query>` for deterministic substring search over doc id, title, path, `describes`, and `tests`
- `irminsul context --changed` for staged, unstaged, and untracked git files
- `irminsul context --change <rfc-id>` as an alias for the [change lifecycle](change.md) status report, so an agent oriented around one RFC gets the same evidence view without switching command groups

Each result reports the owning doc, matching source claims, first declared entrypoint, tests, `depends_on`, docs that depend on it, relevant deterministic findings, and next command hints. `--profile hard|configured|all-available` controls deterministic finding breadth. Ordinary lookups default to `configured`; workflow aliases default to `hard` so the frequent edit loop does not pay for every soft audit unless requested.

## Editing workflow

The common agent loop is expressed as two stateless workflow aliases over those
input modes:

- `irminsul context --before-edit <path...>` resolves one or more source or doc
  paths in one graph pass, groups them by owner, and adds active draft/accepted
  RFCs whose explicit `affects` list names that owner. Parsed requirement ids and
  declared tests are included without inferring relationships from prose.
- `irminsul context --after-edit` inspects staged, unstaged, and untracked paths,
  routes both owned source files and explicitly declared tests, and runs the
  configured hard checks even if no changed path has an owner. Its exit code is
  1 when hard validation fails.

Workflow JSON keeps the underlying lookup `mode` (`path` or `changed`) and adds
`workflow`, `validation`, per-result `active_changes`, and ordered
`next_actions`. Ordinary context calls retain their existing JSON shape. The
actions are explicit command-and-reason pairs derived from report state, not an
interactive session or an AI recommendation.

## Scope & Limitations

Topic search is plain substring matching, not fuzzy search. `--changed` and
`--after-edit` depend on `git status --porcelain` via the shared
`irminsul.git.changes` helper (also used by the [change lifecycle](change.md) for
its local diff baseline); outside a git worktree they report the git error
instead of guessing. Workflow modes do not include document excerpts, rank
relationships, apply token budgets, or persist session state; those are separate
retrieval concerns.
