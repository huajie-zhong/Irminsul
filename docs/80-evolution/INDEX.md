---
id: 80-evolution
title: Evolution
audience: reference
tier: 4
status: draft
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Evolution

Where the system is going. Roadmap, RFCs in flight, risks, debt, deprecations.

## Requests for Comments (RFCs)

RFCs are *proposals before decisions*. They live in `rfcs/` while in flight. The lifecycle:

- **Draft** — author iterates privately or with a small group.
- **Open** — opened for comment. PR comments work; for larger changes use a dedicated discussion thread.
- **Final Comment Period** — explicit "last call" window of N days. Changes during FCP are minor only.
- **Resolved** — Accepted (converts to ADR; RFC marked with the ADR number), Rejected (stays with `Status: Rejected` and reasoning), or Withdrawn.

Two requirements that prevent RFCs from festering:

- **Decision Owner.** One person is named in the RFC frontmatter as accountable for driving it to resolution. Without an owner, RFCs sit open for months.
- **Target Decision Date.** Set at draft time. CI auto-pings the Decision Owner if the date passes without resolution, and after a grace period auto-marks the RFC `Status: Stalled`.

When an RFC becomes an ADR, both link to each other. The RFC stays in `rfcs/` for archival; the ADR is the canonical record going forward.
