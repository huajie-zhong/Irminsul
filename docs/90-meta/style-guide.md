---
id: style-guide
title: Style Guide
audience: reference
tier: 3
status: stable
describes: []
---

# Style Guide

Authoring conventions for docs in this repository. For the doc system's structural rules, see [`CONTRIBUTING.md`](../CONTRIBUTING.md). This guide covers style choices that the tooling does not enforce.

## Doc IDs

The `id` field must match the filename stem. For layer index docs (`INDEX.md`), the id is the layer directory name (e.g., `20-components`). Never use path segments or slashes in an id — bare slugs only. <!-- irminsul:ignore prose-file-reference reason="filename convention example" -->

## Tier assignments

| Layer prefix | Tier | Rationale |
|---|---|---|
| 00-foundation, 10-architecture, 50-decisions | T2 | Stable; change rarely |
| 20-components, 30-workflows, 60-operations, 70-knowledge, 80-evolution | T3 | Living; change often |
| 40-reference | T1 | Generated; do not edit by hand |
| 90-meta | T3 | Living meta-docs |

## Audience values

Pick the value that matches how the reader arrives at the doc:

- `explanation` — reader wants to understand how something works
- `reference` — reader is looking up a specific fact
- `tutorial` — reader is learning by doing (step-by-step, follows along)
- `meta` — doc is about the doc system itself (use only in 90-meta)

## Claims syntax (foundation docs only)

Docs in `00-foundation/` and `10-architecture/` may carry structured claims in frontmatter. Each claim needs an `id`, `state`, `kind`, `claim`, and `evidence` list. Valid states are `enabled`, `available`, `external`, and a pending-RFC state for work not yet shipped. Reference claims in body prose with `<!-- claim:<id> -->`.

## Prose conventions

- Write in present tense. "The check returns findings" not "The check will return findings."
- Avoid version-specific references or forward-looking language in living docs (e.g., 'ships in vN.N', 'coming soon'). Move such content to an RFC.
- One sentence per idea. Compound sentences obscure the main point.
- Limit `## Scope & Limitations` to what the component genuinely does not do. Do not list things it does not do by accident; only list things that could be confused with its purpose.

## Scope & Limitations

This guide covers prose style and convention choices only. Structural rules (frontmatter fields, link targets, glob patterns) are enforced by `irminsul check` and documented in [`CONTRIBUTING.md`](../CONTRIBUTING.md) and the [`40-reference`](../40-reference/) layer.
