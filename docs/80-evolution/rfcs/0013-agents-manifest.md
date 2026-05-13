---
id: 0013-agents-manifest
title: "RFC-0013: AGENTS.md agent navigation manifest"
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0013: AGENTS.md agent navigation manifest

## Summary

Add a required `docs/AGENTS.md` manifest that gives agents a curated entry
point into the documentation tree, backed by generated navigation data so it
does not rot.

## Motivation

New agents have no curated entry into `docs/`. `CLAUDE.md` covers code-facing
guidance, but nothing covers the documentation tree. `irminsul context` answers
per-task questions, but it is not a map.

## Detailed Design

Require `docs/AGENTS.md` with three stable sections:

- A generated tree-by-layer and tier table with doc id, title, audience, and an
  optional one-line `summary` frontmatter field.
- A curated foundation-principles digest of roughly 40 lines covering the Three
  Laws, the nine-layer overview, and the three-tier overview.
- A task playbook table mapping common agent tasks to relevant docs, checks,
  and commands.

Add a hard `agents-manifest` check that errors when:

- `docs/AGENTS.md` is missing.
- The generated section has drifted from the current doc graph.
- Required `Foundations` or `Task Playbook` headings are absent.

Add a regeneration target:

```text
irminsul regen agents-md
```

`irminsul fix` should auto-regenerate the generated section while preserving
the curated foundations and task playbook sections.

## Alternatives

- Static `docs/90-meta/agent-index.md`. Rejected because RFC 0011 already chose
  the task-scoped `irminsul context` command over a broad static index.
- Pure-curated `AGENTS.md`. Rejected because it will rot as the documentation
  tree changes.
- Pure-generated `AGENTS.md`. Rejected because generated data alone loses the
  foundation framing agents need before editing docs.
