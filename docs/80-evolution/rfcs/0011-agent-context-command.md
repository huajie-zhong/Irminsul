---
id: 0011-agent-context-command
title: "RFC-0011: Agent context command"
audience: explanation
tier: 2
status: stable
describes: []
---

# RFC 0011: Agent context command

## Summary

Add `irminsul context` as an interactive CLI lookup for agents and contributors. It replaces the generated agent discovery index idea with a runtime command that answers the current task shape directly.

Supported forms:

```bash
irminsul context <path>
irminsul context --topic <query>
irminsul context --changed
irminsul context --format json <path>
```

There is no generated Markdown fallback.

## Motivation

Agents need a fast way to answer practical navigation questions before editing:

- Which doc owns this source path?
- Which tests validate this component?
- Which docs depend on it, and which docs does it depend on?
- Which deterministic findings are relevant to this path or owning doc?
- Which command should be run next?

A static index becomes either too broad or stale in the moment. A command can use the current `DocGraph`, current git status, and current deterministic findings without committing a generated artifact.

## Detailed Design

`irminsul context` builds the `DocGraph` and supports exactly one input mode per invocation:

- `<path>`: source or doc path context
- `--topic <query>`: deterministic substring search over doc id, title, path, `describes`, and `tests`
- `--changed`: staged, unstaged, and untracked files from git

For each owning doc result, the command prints:

- owning doc id, title, and path
- matching source claims and first declared entrypoint
- declared tests
- `depends_on` and depended-on-by docs
- relevant deterministic findings for the owning doc or requested path
- next command hints such as `irminsul check --profile hard`, `irminsul list undocumented`, or `irminsul regen docs-surfaces`

`--profile configured|all-available` controls deterministic finding breadth only. LLM checks are excluded.

`--format json` emits stable top-level fields:

- `version`
- `mode`
- `results`
- `unmatched`

## Changed Files Mode

`--changed` shells out to `git status --porcelain --untracked-files=all`, groups owned files by owning doc, and reports unclaimed or ambiguous files in `unmatched`. It does not try to infer ownership for docs that fail frontmatter parsing.

## Removal

Remove `irminsul regen agent-index`, remove `docs/90-meta/agent-index.md`, and keep `irminsul regen all` limited to configured generated artifacts such as language reference stubs and docs surfaces.

## Drawbacks

The command does more work per invocation than reading a static file because it builds the graph and runs deterministic checks. That cost is acceptable because context lookup is task-scoped and avoids maintaining another generated document.

## Alternatives

- Generate a static `docs/90-meta/agent-index.md`. Rejected because the output is necessarily broad and still requires agents to filter it manually.
- Ask an LLM to summarize the repo. Rejected because ownership, dependencies, and findings must come from deterministic sources.
- Keep only `grep describes:` guidance. Rejected because it does not answer dependency, test, finding, or changed-file questions.
