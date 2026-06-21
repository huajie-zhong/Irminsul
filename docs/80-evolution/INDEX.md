---
id: 80-evolution
title: Evolution
audience: reference
tier: 4
status: stable
describes: []
children:
  - patterns
---

# Evolution

Where the system is going. Roadmap, RFCs in flight, risks, debt, deprecations.

- [`patterns`](patterns.md) — failure patterns and the system rules that prevent them

## Requests for Comments (RFCs)

See [`rfcs`](rfcs/INDEX.md) for the current RFC list.

RFCs are *proposals before decisions*. They live in `rfcs/` while in flight. The lifecycle:

- **Draft** — author iterates privately or with a small group.
- **Open** — opened for comment. PR comments work; for larger changes use a dedicated discussion thread.
- **Final Comment Period** — explicit "last call" window of N days. Changes during FCP are minor only.
- **Resolved** — Accepted (converts to ADR; RFC marked with the ADR number), Rejected (stays with `Status: Rejected` and reasoning), or Withdrawn.

To keep RFCs from festering, set an optional **Target Decision Date** (`target_decision_date`) in the frontmatter. The `rfc-resolution` check warns once that date passes without the RFC being resolved, so a stalled proposal surfaces on the next `irminsul check`.

When an RFC becomes an ADR, both link to each other. The RFC stays in `rfcs/` for archival; the ADR is the canonical record going forward.
