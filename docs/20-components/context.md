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
- `irminsul context --topic <query>` for deterministic tokenized search over doc id, title, path, `describes`, `tests`, `tags`, and `summary`: every whitespace-separated term in the query must appear as a substring somewhere in that set (terms may hit different fields), so multi-word queries no longer need to match as one literal phrase
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

## How the two modes pair

The aliases encode a stateless inspect–edit–verify loop. Nothing is written to
disk between the calls; each run re-derives its answer from the current graph
and git status, so the loop is safe to re-enter and cannot drift.

| | `--before-edit <path...>` | `--after-edit` |
|---|---|---|
| Input | paths you name, resolved through `path` mode | staged/unstaged/untracked paths, via `changed` mode |
| Owner routing | doc paths match directly; source paths match the most specific `describes` glob | same, plus files listed in a doc's `tests:` route to that doc |
| Default profile | `hard` | `hard` |
| Exit code | non-zero only if a named path has no owner | non-zero when hard validation reports errors |
| Purpose | load the packet **before** you touch code | prove the working tree is still consistent **after** |

Both modes attach the deterministic next step. `--before-edit` always closes
with a pointer to `--after-edit`; `--after-edit` adds a `co-change` reminder and
a `irminsul context <owner-doc>` action for any source file whose owning doc was
not edited in the same change, plus `irminsul check --profile hard` when hard
validation fails. Active draft/accepted RFCs whose `affects` list names an owner
surface in both modes with a `irminsul change status <id>` action.

## Example: the edit loop end to end

Suppose an agent is about to change `src/irminsul/context.py`. It packages the
owning knowledge first:

```console
$ irminsul context --before-edit src/irminsul/context.py
Workflow: before-edit

owner: context (docs/20-components/context.md)
  input: src/irminsul/context.py
  source claims: src/irminsul/context.py
  tests: tests/test_cli_context.py, tests/test_context_unit.py
  depends_on: checks (...), config (...), docgraph (...)
  depended-on-by: cli (...), mcp-server (...)
  active changes:
    0037-workflow-context-modes [draft] (docs/80-evolution/rfcs/0037-workflow-context-modes.md)
      requirements: package-pre-edit-context, validate-post-edit-impact, ...
  findings: (none)

Hard validation: passed (0 errors, 0 warnings)
Next actions:
  irminsul change status 0037-workflow-context-modes
    reason: Active RFC explicitly affects component 'context'.
  irminsul context --after-edit
    reason: Validate the working tree and affected repository knowledge after editing.
```

The agent now knows which doc owns the file, which tests guard it, that an
active RFC affects it, and exactly what to run next. After editing the code —
but forgetting to update the owning doc — it runs the paired verify:

```console
$ irminsul context --after-edit
Workflow: after-edit

owner: context (docs/20-components/context.md)
  input: src/irminsul/context.py
  co-change: owning doc not updated in this change
  findings: (none)

Hard validation: passed (0 errors, 0 warnings)
Next actions:
  irminsul context docs/20-components/context.md
    reason: Owning document 'context' was not updated in this change.
```

`after-edit` exits non-zero if hard validation reports errors, so the same
command doubles as a gate in a pre-commit hook or CI step. Add `--format json`
to either call to drive the loop from a script; the workflow fields
(`workflow`, `validation`, `active_changes`, `next_actions`) are additive over
the ordinary context JSON.
## Content excerpts

Workflow packets include authored content by default: the owning document's
first substantive prose block, its structured claim text, and requirement prose
from active RFCs that explicitly affect it. Each excerpt identifies its category,
source doc/path, title, inclusion reason, and whether it was truncated, so an
agent can use the content without guessing why it appeared.

`--include` accepts a comma-separated selection of `owner`, `claims`,
`requirements`, and `dependencies`; `all` selects every category and `none`
suppresses content. Primitive path/topic/changed lookups remain metadata-only
unless this flag is supplied. `dependencies` means direct authored `depends_on`
relationships and is not part of the workflow default.

Selection is fixed rather than ranked: owner, claims in authored order, active
RFCs by path with requirements in authored order, then dependencies by path.
Each excerpt is limited to 20 lines and 1,200 characters, and each owner result
contains at most eight excerpts. The JSON `content.omitted` map reports eligible
items left out by that cap.

## Scope & Limitations

Topic search is deterministic per-term substring matching (every term must hit, in any field), not fuzzy or semantic search; matches rank by exact-id match, then whole-phrase hit, then how many distinct fields the terms covered. `--changed` and
`--after-edit` depend on `git status --porcelain` via the shared
`irminsul.git.changes` helper (also used by the [change lifecycle](change.md) for
its local diff baseline); outside a git worktree they report the git error
instead of guessing. Content extraction does not rank relationships, estimate
tokens, perform semantic search, or persist session state; those remain separate
retrieval concerns.
