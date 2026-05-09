---
id: 80-evolution
title: Evolution
audience: reference
tier: 4
status: draft
describes: []
children:
  - patterns
---

# Evolution

Where the system is going. Roadmap, RFCs in flight, risks, debt, deprecations.

- [`patterns`](patterns.md) — failure patterns and the system rules that prevent them

## Requests for Comments (RFCs)

In-flight proposals:

- [`0001-topology-b-and-format-json`](rfcs/0001-topology-b-and-format-json.md) — Topology B (sibling code repos) and `--format=json` for check output
- [`0002-fix-and-regen-typescript`](rfcs/0002-fix-and-regen-typescript.md) — `irminsul fix` auto-remediation and TypeScript reference regen
- [`0003-vscode-extension`](rfcs/0003-vscode-extension.md) — VS Code extension (Phase 3)

RFCs are *proposals before decisions*. They live in `rfcs/` while in flight. The lifecycle:

- **Draft** — author iterates privately or with a small group.
- **Open** — opened for comment. PR comments work; for larger changes use a dedicated discussion thread.
- **Final Comment Period** — explicit "last call" window of N days. Changes during FCP are minor only.
- **Resolved** — Accepted (converts to ADR; RFC marked with the ADR number), Rejected (stays with `Status: Rejected` and reasoning), or Withdrawn.

Two requirements that prevent RFCs from festering:

- **Decision Owner.** One person is named in the RFC frontmatter as accountable for driving it to resolution. Without an owner, RFCs sit open for months.
- **Target Decision Date.** Set at draft time. CI auto-pings the Decision Owner if the date passes without resolution, and after a grace period auto-marks the RFC `Status: Stalled`.

When an RFC becomes an ADR, both link to each other. The RFC stays in `rfcs/` for archival; the ADR is the canonical record going forward.
