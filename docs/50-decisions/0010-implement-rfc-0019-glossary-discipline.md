---
id: 0010-implement-rfc-0019-glossary-discipline
title: "ADR-0010: Implement RFC-0019 glossary discipline"
audience: adr
tier: 2
status: stable
describes: []
implements:
  - 0019-glossary-discipline
summary: Rename the glossary check to `glossary-discipline` and enforce explicit glossary metadata for term usage, forbidden synonyms, and glossary links.
---

# ADR-0010: Implement RFC-0019 glossary discipline

## Status

Accepted, 2026-05-19.

## Context

[RFC-0019](../80-evolution/rfcs/0019-glossary-discipline.md) proposed a
deterministic check that keeps glossary terms connected to documentation usage.
The existing `glossary` check only caught one narrow case: a glossary term
redefined as a heading elsewhere. It did not parse term metadata, detect
forbidden synonyms, warn on unused declared terms, or nudge authors to link
first uses back to the glossary.

The RFC also left two policy choices unresolved: whether plural and variant
forms should be inferred, and whether missing glossary links should be checked
globally or opt-in per document.

## Decision

Implement RFC-0019 as a replacement check named `glossary-discipline`.

- Rename the settings table to `[checks.glossary_discipline]` and keep
  `glossary_path` as the only setting used by the check.
- Parse level-2 glossary headings with optional metadata lines:
  `match`, `forbidden_synonyms`, and `case_sensitive`.
- Keep bare headings valid. They continue to support the legacy redefinition
  warning, but RFC-0019 usage and synonym rules only apply when metadata is
  declared.
- Use explicit `match` strings only. Plurals, casing variants, and aliases must
  be listed intentionally.
- Run the missing glossary-link advisory globally at `info` severity, with one
  finding per term per doc.
- Emit forbidden synonym and unused declared-term findings as warnings. Existing
  `--strict` behavior is the opt-in path for making those warnings block CI.

## Alternatives Considered

- **Keep the old `glossary` check name.** Rejected because the RFC explicitly
  names `glossary-discipline` and the new behavior is broader than the old
  check.
- **Alias old and new names.** Rejected to avoid two public registry names for
  the same behavior during the alpha period.
- **Infer plural forms automatically.** Rejected because technical prose,
  acronyms, and code names make language heuristics noisy. Explicit matches
  keep findings defensible.
- **Require per-doc opt-in for missing glossary links.** Rejected because the
  docs most likely to drift are also the least likely to remember the opt-in.
  Info severity keeps the global rule advisory.

## Consequences

Projects using `soft_deterministic = ["glossary"]` must rename the check to
`glossary-discipline`, and projects with `[checks.glossary]` must rename that
table to `[checks.glossary_discipline]`.

Glossary entries can migrate incrementally. A bare heading remains
valid; adding metadata opts the term into usage, synonym, and link discipline.
Auto-link rewriting remains part of RFC-0022 rather than this decision.
