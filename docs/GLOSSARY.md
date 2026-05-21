# Glossary

Vocabulary used across Irminsul's codebase and docs. A single `GLOSSARY.md` is
the authoritative dictionary for all domain terms. Entries may declare exact
matches, rejected synonyms, and case sensitivity for `glossary-discipline`.

## ADR

match: ["ADR", "ADRs", "Architecture Decision Record"]
forbidden_synonyms: []
case_sensitive: true

The canonical, append-only record of a design decision and the reasoning
behind it, stored in `docs/50-decisions/`.

## Doc atom

match: ["Doc atom", "Doc atoms", "doc atom", "doc atoms"]
forbidden_synonyms: []
case_sensitive: true

A single Markdown file with frontmatter. The smallest unit Irminsul tracks.

## DocGraph

match: ["DocGraph", "doc graph"]
forbidden_synonyms: []
case_sensitive: true

The in-memory graph of all doc atoms in a repo, built once per
`irminsul check` invocation.

## Hard check

match: ["Hard check", "hard check", "hard checks"]
forbidden_synonyms: []
case_sensitive: true

A deterministic check whose errors block CI.

## LanguageProfile

match: ["LanguageProfile", "LanguageProfiles"]
forbidden_synonyms: []
case_sensitive: true

A bundle of source-root candidates and schema-leak regex patterns for one
programming language.

## RFC

match: ["RFC", "RFCs", "Request for Comments"]
forbidden_synonyms: []
case_sensitive: true

A proposed feature or change in-flight, stored in `docs/80-evolution/rfcs/`
for review and feedback before final resolution.

## Soft check

match: ["Soft check", "soft check", "soft checks"]
forbidden_synonyms: []
case_sensitive: true

An advisory check. It emits findings but does not fail CI unless the project
runs configured checks with `--strict`.

## Specificity

match: ["Specificity", "specificity"]
forbidden_synonyms: []
case_sensitive: true

The ranking by which uniqueness picks the most-specific `describes` claim.
Fewer wildcards and more literal segments mean higher specificity.

## Tier

match: ["Tier", "tier", "tiers"]
forbidden_synonyms: []
case_sensitive: true

The maintenance category of a doc atom: 1 generated, 2 stable, 3 living, or 4
ephemeral.

## Anti-glossary

- Don't say *Linter*; Irminsul is a *checker*. Linters are line-level; Irminsul works at the graph level.
- Don't say *Documentation generator*; Irminsul *enforces structure*. The renderer is one optional component.
