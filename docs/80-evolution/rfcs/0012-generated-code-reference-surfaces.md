---
id: 0012-generated-code-reference-surfaces
title: Generated code reference surfaces
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0012: Generated code reference surfaces

## Summary

Generate reference docs for facts that already have a code source of truth:
frontmatter fields, CLI commands, and check registries first; config schema and
renderer options later.

## Motivation

The foundation docs say code-derived facts should be generated from code. Manual
lists in explanation docs drift, even when they are structured enough to audit.
RFC 0009 adds drift checks, but the correct long-term shape is to remove manual
copies and make explanation docs link to generated references.

## Detailed Design

Add a docs-surface regeneration path:

```text
irminsul regen --language=docs-surfaces
```

The first generated files live under `docs/40-reference/`:

- `frontmatter-fields.md` from `DocFrontmatter.model_fields`
- `cli-commands.md` from the Typer command tree
- `check-registries.md` from hard, soft deterministic, and LLM registries

Each file is a normal doc atom with stable frontmatter and a generated marker.
RFC 0009 drift checks compare the committed files to current generated output
and tell maintainers to rerun regen when they differ.

## CI Policy

Pull request checks should verify generated references are current. Nightly jobs
may rerun regen and open maintenance PRs, but nightly regeneration is not a
substitute for PR-time validation because stale generated facts should not merge.

## Future Work

Later versions can extend this surface to config models, renderer options,
language profiles, and machine-readable command option details.

## Alternatives

- Keep manual structured sections in component docs. Rejected as the canonical
  policy because it preserves duplicate truth.
- Generate references only nightly. Rejected because stale docs could merge
  before the nightly job catches them.
