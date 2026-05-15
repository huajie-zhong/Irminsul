---
id: 0013-agents-manifest
title: "RFC-0013: AGENTS.md agent navigation manifest"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
resolved_by: docs/50-decisions/0004-agents-manifest.md
followups: []
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
- A pointer to the agent lifecycle protocol defined in
  [`0016-agent-lifecycle-protocol`](0016-agent-lifecycle-protocol.md). The
  manifest exposes the protocol's work order via a one-paragraph summary and
  a deep link, so the protocol stays single-source. The full protocol lives
  at `docs/90-meta/agent-protocol.md`.

Add a hard `agents-manifest` check that errors when:

- `docs/AGENTS.md` is missing.
- The generated section has drifted from the current doc graph.
- Required `Foundations` or `Protocol` headings are absent.

Add a regeneration target:

```text
irminsul regen agents-md
```

`irminsul fix` should auto-regenerate the generated section while preserving
the curated foundations section and the protocol-summary section. The fix
mechanics are part of RFC-0022.

## Relationship to Existing RFCs

- Builds on the agent context command in
  [`0011-agent-context-command`](0011-agent-context-command.md): the manifest
  is the structural map, `irminsul context` answers per-task questions.
- Surfaces the backlinks command in
  [`0014-backlinks-and-refs`](0014-backlinks-and-refs.md) as a recommended
  step before renames or moves.
- Delegates protocol content to
  [`0016-agent-lifecycle-protocol`](0016-agent-lifecycle-protocol.md). The
  manifest summarizes; the protocol owns.
- Depends on the auto-fix expansion in
  [`0022-universal-fix-coverage`](0022-universal-fix-coverage.md) for the
  AGENTS.md regeneration fix.

## Alternatives

- Static `docs/90-meta/agent-index.md`. Rejected because RFC 0011 already chose
  the task-scoped `irminsul context` command over a broad static index.
- Pure-curated `AGENTS.md`. Rejected because it will rot as the documentation
  tree changes.
- Pure-generated `AGENTS.md`. Rejected because generated data alone loses the
  foundation framing agents need before editing docs.

## Resolution

Accepted and resolved by [`ADR-0004`](../../50-decisions/0004-agents-manifest.md).

Landed: `docs/AGENTS.md` with the generated documentation-tree section plus
curated Foundations and Protocol sections; the `irminsul regen agents-md`
target; and the hard `agents-manifest` check (registered and accepted in
`checks.hard`, enabled in this repo's `irminsul.toml`).

Deferred and documented elsewhere:

- `irminsul fix` auto-regeneration of the manifest belongs to
  [`0022-universal-fix-coverage`](0022-universal-fix-coverage.md).
- The canonical lifecycle protocol document under `docs/90-meta/` belongs to
  [`0016-agent-lifecycle-protocol`](0016-agent-lifecycle-protocol.md). Until it
  lands, the manifest's Protocol section deep-links to RFC 0016.
- Making `agents-manifest` a default-on hard check for every consuming project
  is a later rollout step; it currently ships opt-in.
