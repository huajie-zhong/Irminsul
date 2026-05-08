---
id: patterns
title: Evolution Patterns
audience: explanation
tier: 2
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Evolution Patterns

The system is designed to absorb change without rewrites. Here are the recipes.

## Adding a New Feature
1. Open an RFC in `80-evolution/rfcs/`. Get feedback.
2. On acceptance: convert to ADR in `50-decisions/`, mark RFC `Accepted → see ADR-XXXX`.
3. Implement: code + tests + relevant doc updates in one PR.
4. New components get new files in `20-components/`. New cross-cutting flows get files in `30-workflows/`. The reference layer regenerates itself.
5. If new domain terms appear, add them to `GLOSSARY.md` in the same PR.

## Changing Philosophy (the hardest case)
Philosophy changes — switching from REST to event-driven, from monolith to services, from optimistic to pessimistic concurrency — touch many docs. The system handles this via:

- **One ADR captures the decision** (e.g., "ADR-0078: Move to event-driven architecture")
- **`00-foundation/principles.md` is updated** with a brief note pointing to the ADR
- **Affected component docs are updated** with explicit "Previously: X. Now: Y. See ADR-0078." callouts
- **Old workflow docs are not deleted** — they're marked `status: deprecated` and remain searchable, with a banner pointing to the replacement

The point: philosophy changes leave a clear trail. A new contributor reading `principles.md` sees the current philosophy and the link to the ADR explaining why it changed.

## Deprecating a Component
1. New ADR explaining the deprecation and replacement.
2. Set `status: deprecated` on the component doc.
3. CI auto-injects a deprecation banner with timeline and migration guide link.
4. Add to `80-evolution/deprecations.md` with target removal date.
5. On removal: delete the component, but keep the doc for one full release cycle marked `status: removed`.

## Splitting an Overgrown Doc
When a doc exceeds ~500 lines or its `depends_on` field grows beyond ~8 entries, split it. Keep the original ID as a hub doc that links to the new pieces. CI's drift and link checks will catch any references that broke.

## Merging Redundant Docs
If two docs cover overlapping ground (which the duplication detector should catch), pick a canonical one, redirect the other via `supersedes`, and let the link rewriter update inbound references in a follow-up PR.
