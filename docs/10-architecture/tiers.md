---
id: tiers
title: The Tier System
audience: explanation
tier: 2
status: stable
describes: []
depends_on:
  - doc-atom
---

# The Tier System

Not every doc deserves the same treatment. We classify each doc by how it's maintained to dictate its enforcement policy.

| Tier | Name | Edited By | Review Cadence | Examples |
|------|------|-----------|----------------|----------|
| T2 | Stable | Humans, rarely | On structural change | Principles, architecture overview, ADRs |
| T3 | Living | Humans, often | Quarterly | Component docs, workflows, runbooks |
| T4 | Ephemeral | Anyone | Discarded after use | Sprint plans, RFCs in flight |

Tier dictates enforcement:
- **T3 docs** trigger drift warnings if their `describes` files change without them.
- **T4 docs** auto-archive after a deadline.

There is no T1. The old "Generated" tier held CI-built reference under
[`40-reference/`](../50-decisions/0014-retire-tier-1-and-reference-layer.md); it
was retired along with that layer when derivable surfaces moved on-demand to
`irminsul surface`. The numbering is kept (T2–T4) so existing `tier:`
frontmatter stays valid.
