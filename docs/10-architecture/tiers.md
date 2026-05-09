---
id: tiers
title: The Tier System
audience: explanation
tier: 2
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
depends_on:
  - doc-atom
---

# The Tier System

Not every doc deserves the same treatment. We classify each doc by how it's maintained to dictate its enforcement policy.

| Tier | Name | Edited By | Review Cadence | Examples |
|------|------|-----------|----------------|----------|
| T1 | Generated | CI only | Never | API reference, type schemas, config reference |
| T2 | Stable | Humans, rarely | On structural change | Principles, architecture overview, ADRs |
| T3 | Living | Humans, often | Quarterly | Component docs, workflows, runbooks |
| T4 | Ephemeral | Anyone | Discarded after use | Sprint plans, RFCs in flight |

Tier dictates enforcement:
- **T1 docs** are in `.gitignore` and rebuilt every PR.
- **T3 docs** trigger drift warnings if their `describes` files change without them.
- **T4 docs** auto-archive after a deadline.
