---
id: 0014-retire-tier-1-and-reference-layer
title: "ADR-0014: Retire Tier 1 and the reference layer"
audience: adr
tier: 2
status: stable
describes: []
summary: Remove the Tier 1 ("Generated") tier and the 40-reference layer; non-derivable reference lives in its owning layer, derivable surfaces stay on-demand.
---

# ADR-0014: Retire Tier 1 and the reference layer

## Status

Accepted, 2026-05-31. Resolves [`0026-retire-tier-1-and-reference-layer`](../80-evolution/rfcs/0026-retire-tier-1-and-reference-layer.md). Supersedes the "keep the `40-reference` layer" clause of [`ADR-0013`](0013-retire-render-subsystem.md).

## Context

RFC-0025 retired the renderer and the `regen python`/`typescript` stubs, removing
every artifact that was ever generated into `40-reference/`. ADR-0013 kept the
layer "for hand-written reference," but it then held only its own index doc. Tier 1
("Generated") was defined as "gitignored, rebuilt every PR" — a mechanic with no
remaining inhabitant — and the only file its `[tiers].generated` glob matched was a
hand-written index doc mistagged `tier: 1`. A layer keyed on format rather than
fact-ownership also competes with Law 1's "one home per fact."

## Decision

Remove Tier 1 from the tier model and remove the `40-reference/` layer in full,
including its scaffold. Drop the `[tiers].generated` config field and the
generated-doc exemption it powered in the `liar` and `reality` checks. Keep the
T2–T4 numbering unchanged so existing `tier:` frontmatter stays valid. Non-derivable
reference facts live in their owning layer (`20-components/`, `50-decisions/`, …);
derivable surfaces stay on-demand via `irminsul surface`.

## Alternatives Considered

- **Keep `40-reference` as a hand-written reference home (ADR-0013's stance).**
  Rejected: it held no content, and a format-keyed layer competes with the
  fact-owning layer under Law 1.
- **Keep `[tiers].generated` as an empty-default field for downstream repos that
  still commit generated docs.** Rejected: it contradicts the now-explicit
  "derive, don't materialize; don't commit generated docs" position; `extra =
  "forbid"` means a stale `generated =` key fails loudly with a clear fix.
- **Renumber the remaining tiers T1–T3.** Rejected: it would rewrite the `tier:`
  field on every doc for no semantic gain; the unused slot is cheaper to retire in
  place.

## Consequences

- The tier model is T2 (Stable), T3 (Living), T4 (Ephemeral); there is no T1.
- The layer set is `00,10,20,30,50,60,70,80,90`.
- `liar` and `reality` no longer special-case generated docs; the code path is
  simpler and there is nothing left to exempt.
- Downstream `irminsul.toml` files carrying `[tiers].generated` must drop the key;
  the validation error names it directly.
