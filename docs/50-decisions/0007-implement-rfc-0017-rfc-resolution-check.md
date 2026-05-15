---
id: 0007-implement-rfc-0017-rfc-resolution-check
title: "ADR-0007: Implement RFC-0017 RFC resolution check"
audience: adr
tier: 2
status: stable
describes: []
summary: Add the `rfc-resolution` soft deterministic check and a `--now` override so the RFC lifecycle is machine-enforced end to end.
---

# ADR-0007: Implement RFC-0017 RFC resolution check

## Context

[RFC-0017](../80-evolution/rfcs/0017-rfc-resolution-check.md) proposed a
deterministic soft check named `rfc-resolution` that enforces the RFC
lifecycle: accepted RFCs become `status: stable` with a bidirectional link to
their decision doc, rejected and withdrawn RFCs carry a rationale section, and
in-flight RFCs that miss their `target_decision_date` get flagged. The
frontmatter schema already required `resolved_by` when `rfc_state: accepted`,
but everything past that bare invariant was prose convention. The PR that
landed RFC-0015 illustrated the gap: nothing prevented an "accepted" RFC from
staying `status: draft` indefinitely.

## Decision

Implement RFC-0017 in full:

- Add `RfcResolutionCheck` (`src/irminsul/checks/rfc_resolution.py`) to the
  soft deterministic registry. It scopes itself to docs under
  `docs/80-evolution/rfcs/`. Per `rfc_state` it enforces: accepted RFCs are
  `status: stable`, `resolved_by` resolves to an existing doc, the decision
  doc links back, the body has a `## Resolution` section, and any
  `## Unresolved Questions` section is non-empty; rejected RFCs are stable and
  carry a `## Resolution` or `## Rejection Rationale` section; withdrawn RFCs
  are stable, carry a `## Withdrawal Rationale` or `## Resolution` section,
  and do not retain a non-empty `## Unresolved Questions`; `draft`, `open`,
  and `fcp` RFCs warn when `target_decision_date` is past, and `open` RFCs
  warn when `decision_owner` is missing.
- Add two optional frontmatter fields (`decision_owner`,
  `target_decision_date`) to the canonical schema, with ISO-date validation
  on the latter.
- Add a `clock` module and a `--now YYYY-MM-DD` flag to `irminsul check`,
  threaded through `build_graph` onto `DocGraph.now`. Update `stale-reaper`
  to consume the same source so date-sensitive checks share one "today".

Back-link verification reuses the graph's `inbound_weak` index — the same
markdown parser that powers the orphans check — so it costs nothing extra at
build time.

## Alternatives Considered

- **Keep RFC lifecycle as prose in the evolution index.** Rejected: agents
  need machine-readable feedback, and prose rules don't gate merges.
- **Move accepted RFCs into the ADR folder.** Rejected: RFCs are useful
  historical artifacts and should stay in the evolution layer; the ADR is the
  canonical record going forward.
- **Treat `status: stable` as the acceptance state.** Rejected: doc
  reliability and proposal outcome are separate concepts. `rfc_state`
  captures the second; conflating them loses the distinction.
- **Mock `datetime.date.today` in tests instead of adding `--now`.** Rejected:
  the RFC explicitly asked for one canonical override so date-sensitive
  checks behave consistently across CI runners and so test fixtures stay
  deterministic without monkeypatching globals.

## Consequences

The check stays soft initially. Projects opt into strict treatment by running
`--profile=configured --strict`. The frontmatter additions are optional so
existing RFCs (0001–0011, which predate `rfc_state`) remain silent until
someone chooses to back-fill them. `--now` becomes the convention for any
future date-sensitive check, and `stale-reaper` already follows it.
