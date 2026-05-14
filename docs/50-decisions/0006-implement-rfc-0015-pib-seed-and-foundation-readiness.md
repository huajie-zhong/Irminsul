---
id: 0006-implement-rfc-0015-pib-seed-and-foundation-readiness
title: "ADR-0006: Implement RFC-0015 PIB seed and foundation readiness"
audience: adr
tier: 2
status: stable
describes: []
summary: Add `irminsul seed` and the `foundation-readiness` check, with an opt-in seed prompt on interactive fresh-start init.
---

# ADR-0006: Implement RFC-0015 PIB seed and foundation readiness

## Context

[RFC-0015](../80-evolution/rfcs/0015-pib-seed-and-foundation-readiness.md)
proposed a first-class seed flow for projects that begin with only a principle,
idea, and belief. Fresh-start `init` leaves the foundation as scaffold
placeholders, so a project can move into architecture and code before its root
intent is ever written down, and the lifecycle checks of later RFCs have nothing
to measure against on day one.

## Decision

Implement RFC-0015 in full:

- Add `irminsul seed`, which captures the PIB statement (interactive prompts,
  individual flags, or a `--json` file) and writes the foundation principles
  doc, the architecture overview doc, an anchoring ADR titled from the user's
  idea, and an anchoring RFC. It is idempotent: it writes freely over scaffold
  placeholders, refuses to
  clobber edited foundation docs without `--reseed`, and appends a dated pass
  with `--merge`.
- Add the `foundation-readiness` soft deterministic check, which warns when a
  `00-foundation/` or `10-architecture/` doc still contains a known scaffold
  placeholder phrase. The phrase set lives in
  `src/irminsul/init/placeholders.py` alongside the scaffolds.

This refines RFC-0015 on one point. The RFC rejected adding seed prompts to
`init` over scriptability concerns. Implementation reconciles the two: the
interactive fresh-start path of `init` offers an **opt-in** prompt to run seed
inline, while `init --no-interactive` gains no new prompts and stays fully
scriptable. `irminsul seed` remains the standalone command for capturing or
redoing the seed later.

## Consequences

A fresh-start project can capture real intent immediately after `init`, and the
`foundation-readiness` check keeps an un-seeded foundation visible. The anchoring
RFC gives the evolution layer a non-empty starting point, which the lifecycle
checks proposed by later RFCs depend on. `init` gains one interactive branch and
a new code path that must stay out of the non-interactive flow.
