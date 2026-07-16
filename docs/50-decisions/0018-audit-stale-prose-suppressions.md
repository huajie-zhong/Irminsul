---
id: 0018-audit-stale-prose-suppressions
title: "ADR-0018: Audit stale prose suppressions"
audience: adr
tier: 2
status: stable
describes: []
summary: Report obsolete prose-file-reference exceptions without making them baseline-suppressible or automatically removing them.
---

# ADR-0018: Audit stale prose suppressions

## Status

Accepted, 2026-07-15. Resolves
[`0039-stale-prose-suppressions`](../80-evolution/rfcs/0039-stale-prose-suppressions.md).

## Context

The `prose-file-reference` check permits explicit line and block suppressions for
intentional examples. Those markers can remain after the prose is linked or
removed, leaving an invisible exception that may later hide unrelated text.
Baselines already report stale fingerprints, and inventory drift reports stale
surface omissions, but inline prose exceptions have no equivalent audit.

## Decision

Use the same deterministic unlinked-local-Markdown predicate for ordinary
findings and suppression-use tracking. A line marker is used only when its line
still violates the rule after removing the marker comment. A matched block is
used only when an enclosed, non-fenced line violates the rule.

Report clean markers as informational `stale-suppression` findings with typed
line-or-block scope. Keep informational findings out of baselines, preserve the
existing hard errors for unmatched block markers, and leave removal manual.

## Alternatives Considered

- **Emit warnings.** Rejected because baselines can suppress warnings, hiding the
  audit of the obsolete exception itself.
- **Require typed reasons immediately.** Deferred because reason quality is a
  separate policy and cannot be validated by the underlying deterministic rule.
- **Delete stale markers automatically.** Deferred because paired block editing
  needs a separate safety and idempotence contract.

## Consequences

- Agents see obsolete exception debt without a new blocking gate.
- Marker reasons containing `.md` do not falsely count as suppressed violations.
- Baseline updates cannot make stale suppression findings disappear.
- Removing line and block markers remains an explicit human-reviewed edit.
