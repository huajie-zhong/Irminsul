---
id: 0033-derived-layered-impact
title: "Derived layered impact: the change ripple as a query, not metadata"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0033: Derived layered impact

## Summary

The deep-binding step of the [bound-change loop](0029-bound-change-loop.md). A
change rarely touches one component in isolation — it may ripple up to the
foundation (does it revise a principle?), through architecture (does it add a
component or move the hierarchy?), down to workflows, and across the glossary. This
RFC makes that ripple a **derived view** — `irminsul change impact <id>`, computed
from the diff and the [`DocGraph`](../../20-components/docgraph.md) — and routes each
affected layer to the check that already governs it. Per the derive-don't-declare law
of [`0029`](0029-bound-change-loop.md), the impact is *never stored* in the RFC; it
is recomputed each run, fresh by construction.

## Motivation

A spec tool situates a change in a flat `specs/` folder. irminsul situates docs in a
9-layer typed graph, which means a change can be bound to *all* of it — but only if
the binding is derived rather than declared. The risk, raised during design, is
exactly duplication: writing the touched components, surfaces, and architecture
deltas into the RFC would copy facts that already live in the component
`describes:`, the derived `surface`, and the layer structure. The resolution is to
make impact a query over existing data, so the loop gains layer-wide reach with zero
new home for any fact.

## Detailed Design

### The derived view

`irminsul change impact <id>` reports, for a change RFC, the ripple across layers —
all computed, none stored:

- **Foundation (00).** From the change's `direction: revises` flag (the one
  non-derivable judgment) plus whether the diff touches code a foundation principle
  constrains: surface the principles in play. A `revises` change with no foundation
  doc edit is flagged.
- **Architecture (10).** Detect a new `20-components/*.md` or a moved doc from the
  diff and the parent-child inference
  ([`0004-remove-children-field`](0004-remove-children-field.md)); flag when an
  architecture-altering change leaves `component-hierarchy` / `overview` unupdated,
  reusing the index-graduation and phantom-layer logic.
- **Components (20).** The diff→owner derivation of
  [`0021-code-doc-cochange`](0021-code-doc-cochange.md): which component docs own the
  changed code.
- **Surfaces.** `irminsul surface` ([`surface`](../../20-components/surface.md)):
  which cli/http/exports/env-var identities the change added or removed, governed by
  the watched-surface mechanism
  ([`0027-watched-surfaces`](0027-watched-surfaces.md)).
- **Workflows (30) & glossary.** Touched workflow docs from ownership; new terms the
  change's prose introduces, checked by `glossary-discipline`
  ([`0019-glossary-discipline`](0019-glossary-discipline.md)).

### Routing, not new enforcement

The view does not invent checks. Each layer's drift is already caught by an existing
check; impact is the lens that *gathers* those findings for one change and presents
the ripple. The only genuinely new signal is the foundation `direction` consistency
nudge, which needs the human's `revises` judgment because direction is not derivable.

### Impact altitude (the throttle)

Most changes are component-level and surface a one-line impact. A change pays for
depth only where it actually reaches: a typo fix shows components and nothing else; a
direction pivot shows the full foundation→architecture ripple. The tier/layer
gradient ([`tiers`](../../10-architecture/tiers.md),
[`layers`](../../10-architecture/layers.md)) is the throttle — depth is available and
typed, never mandatory.

## Drawbacks

- **Derivation cost.** Walking the diff against the whole graph per change is more
  work than reading stored metadata; acceptable because it runs on demand, not in the
  hard path by default.
- **Foundation heuristic.** The `direction` consistency check leans on a human flag
  plus coarse code-touch heuristics; it nudges, it does not prove.
- **Presentation surface.** A multi-layer report risks noise; impact altitude and
  default-to-component keep it terse.

## Alternatives

- **Store the layered `impact:` block in the RFC** — the original design, rejected:
  duplicates `describes:`, `surface`, and the layer structure; violates
  derive-don't-materialize and Law 1.
- **A single flat "affected files" list** — rejected: throws away the layer typing
  that is irminsul's advantage over a flat spec tree.
- **No layered view** — leaves the loop bound only at the component level; workable,
  but forfeits the cross-layer consistency that distinguishes the model.

## Unresolved Questions

- Whether `change impact` is its own subcommand or a mode of `context`.
- How precise the foundation `direction` consistency check can be without an LLM,
  given the hard path is deterministic.
- Output format and whether impact joins `irminsul status` as a digest line.
