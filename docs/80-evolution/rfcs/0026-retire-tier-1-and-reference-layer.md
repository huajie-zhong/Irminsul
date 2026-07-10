---
id: 0026-retire-tier-1-and-reference-layer
title: Retire Tier 1 and the dedicated reference layer
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
affects: [frontmatter, checks]
resolved_by: docs/50-decisions/0014-retire-tier-1-and-reference-layer.md
required_updates: []
---

# RFC 0026: Retire Tier 1 and the dedicated reference layer

## Summary

Remove Tier 1 ("Generated") from the tier model and remove the `40-reference/`
layer entirely. Drop the `[tiers].generated` config field and the doc-graph
exemption it powered. Finishes what RFC-0025 started: with no renderer and no
generated reference, there is no committed-and-CI-rebuilt content left for T1 to
describe, and the layer that held it stands empty.

## Motivation

RFC-0025 retired the renderer and the `regen python`/`typescript` stubs. That
removed every artifact that was ever generated *into* `40-reference/`. ADR-0013
kept the `40-reference/` layer "for hand-written reference," but two of the
system's own rules argue against a layer defined by format rather than ownership:

- **Law 1 — one home per fact.** Config, errors, events, and schemas are each
  either *derivable* (answered on demand by `irminsul surface`) or *owned by the
  component* they belong to (`20-components/`). A catch-all "reference" layer
  competes with those homes instead of adding one.
- **Derive, don't materialize** (RFC-0020). Anything reconstructable from code is
  not committed at all; it is recomputed per call so it cannot drift.

Tier 1 is the tier half of the same problem. Its defining mechanic was "in
`.gitignore`, rebuilt every PR." After RFC-0025 nothing in the tree is gitignored
and CI-rebuilt, so T1 has no inhabitants and no live mechanism. The one path the
`[tiers].generated` glob still matched — `40-reference/INDEX.md` — was hand-written
yet tagged `tier: 1`, i.e. self-contradictory. The `phantom-layer` check already
flagged `40-reference/` as a directory with only an `INDEX.md`.

## Detailed Design (what is removed)

- **Tier model:** Tier 1 ("Generated"). The numbering is kept (T2 Stable, T3
  Living, T4 Ephemeral) so existing `tier:` frontmatter stays valid; no doc is
  renumbered.
- **Layer:** `docs/40-reference/` in full, and the scaffold that recreated it
  (`init/scaffolds/docs/40-reference/`).
- **Config:** the `[tiers].generated` field (`Tiers.generated`) and its entry in
  `irminsul.toml` and the scaffold `irminsul.toml.j2`.
- **Check behaviour:** the generated-doc exemption in `liar` and `reality`
  (`doc_reality`). Both consumed `tiers.generated` only to skip generated docs;
  with nothing generated, the exemption is dead and the helpers are removed.

## Explicitly retained

- **`irminsul surface <kind>`** remains the on-demand answer for code-derived
  reference (CLI set, endpoints, exports, env vars).
- **The T2–T4 numbering.** Frontmatter values are unchanged; only the unused T1
  slot is retired.
- **`schema-leak`.** It still forbids type/schema definitions in component docs;
  its guidance now points to code (`irminsul surface`) rather than `40-reference/`.

## Resolution

Accepted and implemented; resolved by
[`ADR-0014`](../../50-decisions/0014-retire-tier-1-and-reference-layer.md). The
tier model is T2–T4, the layer set is `00,10,20,30,50,60,70,80,90`, and
non-derivable reference facts live in their owning layer rather than a dedicated
reference tier.
