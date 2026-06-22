---
id: 0034-base-truth-gate-and-mcp-loop
title: "Base-truth gate and the MCP loop surface"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0034: Base-truth gate and the MCP loop surface

## Summary

The closing iteration of the [bound-change loop](0029-bound-change-loop.md). Two
pieces that make the loop *repeatable* and *agent-native*:

1. **Base-truth gate** — before a new change is proposed, assert the base is still
   true: all previously anchored requirements still hold (coverage, `claim-anchor`,
   co-change clean). This is the beat a spec tool lacks — it stops iteration N+1 from
   compounding iteration N's rot.
2. **MCP loop surface** — expose the loop verbs (propose, requirement/grammar
   validate, change context, accept, impact) as MCP tools, governed as a watched
   surface so they cannot drift from the CLI — reaching "works with any agent"
   through **one** agent-agnostic surface instead of per-tool prompt-file adapters.

## Motivation

The earlier RFCs build a bound forward step and a verifying accept step. What closes
the loop is using the verification to *guard the next forward step*: a proposal
should depart from a base the engine has just confirmed, not from whatever the docs
happen to say. Without this gate, the loop is still linear; with it, every iteration
is grounded.

Separately, the loop is only as good as agents' access to it. Spec tools achieve
broad reach by generating per-tool slash-command files — one adapter per agent, each
a path-and-frontmatter shim. irminsul already chose a cleaner path: an MCP server is
a single surface every MCP-capable agent uses
([`mcp-server`](../../20-components/mcp-server.md)), and
[`0028-mcp-tool-surface-governance`](0028-mcp-tool-surface-governance.md) already
governs that tool set against drift. Putting the loop verbs there gives the whole
propose→accept cycle the same agent-agnostic distribution as the read commands,
without an adapter zoo to maintain.

## Detailed Design

### Base-truth gate

A check / pre-proposal step, `base-truth`, runs the binding guarantees over the
*current* graph: every accepted change's folded requirements
([`0032`](0032-accept-time-anchoring.md)) still have coverage, their anchors still
resolve, and co-change is clean for the touched components. It is the existing
engine pointed at "is the base I am about to build on still true?":

- As a **pre-proposal hint**, it runs when an agent starts a new change (via the MCP
  surface or `irminsul context`), reporting any rotted base before planning.
- As a **gate**, under `--strict` it blocks proposing on a base with unresolved
  drift, forcing the rot to be fixed first — so the forward step always launches
  from truth.

It adds no new check logic; it composes coverage, `claim-anchor`, and co-change into
a single base-readiness verdict, much as [`status`](../../20-components/status.md)
composes health signals today.

### MCP loop surface

The MCP server gains tools for the loop verbs, each a thin wrapper over the same CLI
command an agent would run:

- `propose` (scaffold a bound change RFC — 0029),
- `validate` (requirement grammar — 0030),
- `change_context` (task + progress view — 0031),
- `impact` (derived layered ripple — 0033),
- `base_truth` (the gate above).

Accept-time anchoring (0032) stays a deliberate, reviewable action and is exposed as
a write tool only under the same governance the existing write commands follow. The
new tools are added to `mcp-server.md`'s watched `inventory:` block so
[`0028`](0028-mcp-tool-surface-governance.md)'s mechanism flags any drift between the
tool set and the CLI — the loop surface governs itself.

### Relationship to OpenSpec

This is parity on distribution and a lead on iteration safety. Distribution: one MCP
surface vs. 25+ generated adapter files — same reach, less surface. Iteration safety:
the base-truth gate is the missing beat — a spec tool re-proposes from a canonical
spec nobody re-checked; irminsul re-proposes only after confirming the base holds.

## Drawbacks

- **Gate friction.** A strict base-truth gate can block a proposal because of
  pre-existing, unrelated drift; mitigated by running as a hint by default and a gate
  only under `--strict`.
- **MCP write exposure.** Exposing accept/anchor over MCP widens the write surface;
  constrained to the existing write-command governance and review.
- **Composition cost.** Running coverage + anchors + co-change as a pre-step has a
  latency cost on large repos; it is on-demand, not in every hard run.

## Alternatives

- **Per-agent adapter files** (the spec-tool distribution model) — rejected: a
  copyable path-and-frontmatter lookup table; MCP already gives agent-agnostic reach
  through one governed surface.
- **No base-truth gate** — leaves the loop linear and lets drift compound across
  iterations; this is the precise weakness the stack exists to remove.
- **Fold base-truth into the hard profile unconditionally** — rejected: too coarse;
  it belongs as a hint plus an opt-in `--strict` gate, like the rest of the
  soft-deterministic set.

## Unresolved Questions

- Whether `base-truth` is a check name, a `status` mode, or a `context` pre-step.
- Scoping the gate to the change's `affects` components vs. the whole graph.
- The exact MCP tool names and which loop verbs are read vs. write under
  [`0028`](0028-mcp-tool-surface-governance.md) governance.
- Whether the gate should consult git history (co-change needs a base ref) and how
  that interacts with the deterministic hard path.
