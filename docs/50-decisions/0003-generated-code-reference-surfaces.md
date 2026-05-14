---
id: 0003-generated-code-reference-surfaces
title: "ADR-0003: Generate code-derived reference surfaces"
audience: adr
tier: 2
status: stable
describes: []
summary: Adopt generated reference docs for code-derived surfaces; verify them in CI.
---

# ADR-0003: Generate code-derived reference surfaces

## Status

Accepted, 2026-05-14. Resolves
[`0012-generated-code-reference-surfaces`](../80-evolution/rfcs/0012-generated-code-reference-surfaces.md).

## Context

Foundation policy says code-derived facts belong in generated docs, not hand-maintained
lists in explanation docs. Manual copies of frontmatter fields, the CLI command tree, and
the check registries drift from source even when they are structured enough to audit.

RFC 0012 proposed a `regen docs-surfaces` path plus drift checks. The detailed design
shipped with RFC 0009: `irminsul regen docs-surfaces` writes the generated atoms under
`docs/40-reference/`, and `schema-doc-drift`, `cli-doc-drift`, and `check-surface-drift`
compare the committed files against current generated output. The remaining gap was the
RFC's CI Policy: those drift checks live in `soft_deterministic`, and CI's dogfood job
only ran `--profile=hard`, so they never executed in CI.

## Decision

Adopt generated reference surfaces as the canonical home for code-derived schema, CLI, and
check facts, and close the CI Policy gap by running `irminsul check --profile=configured`
in the dogfood job. The drift checks surface as visible warnings on every pull request,
matching RFC 0009's "run configured warnings in dogfood" guidance.

## Alternatives Considered

- **Keep manual structured sections in component docs.** Rejected: preserves duplicate
  truth that drifts from source.
- **Promote the three drift checks into the hard registry.** Rejected for now: it would
  make a subset of soft checks blocking ahead of a clean advisory baseline, which RFC 0009
  explicitly warned against.
- **Run `--profile=configured --strict` in CI.** Rejected: makes every soft check blocking,
  not just the drift checks.

## Consequences

- Stale generated surfaces are visible on every PR instead of merging silently.
- Component docs stay explanatory and link to the generated references.
- Deferred (RFC 0012 Future Work, not in this decision): extending generated surfaces to
  config models, renderer options, language profiles, and machine-readable command option
  detail. Those land in a follow-up RFC.
