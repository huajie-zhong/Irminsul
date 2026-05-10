---
id: 0011-generated-agent-discovery-index
title: Generated agent discovery index
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0011: Generated agent discovery index

## Summary

Generate a first-hop discovery index for agents and contributors from the
existing doc graph. The index should not depend on an LLM for correctness. It
should mechanically summarize ownership, entrypoints, tests, dependencies,
status, and warning hotspots so an agent can start in the right docs before
editing code.

## Motivation

The root README currently tells agents to search for `describes:` fields. That
works only after the agent knows what it is looking for. Dogfooding showed that
confused agents need a stronger first-hop map:

- Which doc owns this source path?
- Which source file is the component entrypoint?
- Which tests validate the component?
- Which docs depend on this doc?
- Which docs are stale, orphaned, or structurally suspicious?
- Where should a principle, CLI, frontmatter, or check change begin?

Most of this information is already in `DocGraph`, frontmatter, and check
findings.

## Detailed Design

### Generated Artifact

Generate `docs/90-meta/agent-index.md` from deterministic inputs.

The generated index contains:

- source path to owning doc
- component doc to first `describes` entrypoint
- component doc to `tests`
- component doc to `depends_on`
- inbound links and strong dependencies
- status, audience, and tier
- configured-check warning hotspots
- common request routes

### Mechanical Request Routes

Provide generic request routing based on layer conventions and component IDs.

Initial routes:

| Request type | First hops |
|---|---|
| New CLI feature | CLI component doc, command-related component docs, tests. |
| New check | Checks component doc, config component doc, enforcement docs. |
| Frontmatter change | Frontmatter component doc, doc atom doc, templates, tests. |
| Principle or policy change | Foundation docs, enforcement docs, RFC or ADR path. |
| New source module | Owning component doc or undocumented-source listing. |

Projects can later add config overrides for domain-specific routes. LLMs may
summarize the generated index, but they must not be the source of truth for the
index.

### CLI Surface

Add a command after the format stabilizes:

```bash
irminsul regen agent-index
```

The command should be deterministic and produce stable ordering so diffs are
reviewable.

## Implementation Plan

1. Define the generated index format in docs before adding code.
2. Reuse `DocGraph`, inbound indexes, check findings, and the first-is-interface
   convention.
3. Add a deterministic renderer for `agent-index.md`.
4. Add tests for stable ordering and required sections.
5. Update the root README to point agents at the generated index.

## Drawbacks

A generated index can become noisy in large repos. The renderer should group by
component and route type rather than dumping raw graph data.

## Alternatives

- Ask an LLM to generate the index. This may produce readable summaries but can
  hallucinate ownership and omit edge cases.
- Keep only `grep describes:` guidance. This preserves low implementation cost
  but keeps first-hop friction high.

## Unresolved Questions

- Should the generated index live under `90-meta` by default or be configurable?
- Should warning hotspots include only configured checks or support an
  `all-available` audit profile?
