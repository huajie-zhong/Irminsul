# Glossary

Vocabulary used across Irminsul's codebase and docs. A single `GLOSSARY.md` is
the authoritative dictionary for all domain terms. Entries may declare exact
matches, rejected synonyms, and case sensitivity for `glossary-discipline`.

## ADR

match: ["ADR", "ADRs", "Architecture Decision Record"]
forbidden_synonyms: ["design doc", "decision doc"]
case_sensitive: true

The canonical, append-only record of a design decision and the reasoning
behind it, stored in `docs/decisions/`.

## Doc atom

match: ["Doc atom", "Doc atoms", "doc atom", "doc atoms"]
forbidden_synonyms: ["doc node", "Doc node", "doc record", "Doc record", "doc page", "Doc page"]
case_sensitive: true

A single Markdown file with frontmatter. The smallest unit Irminsul tracks.

## DocGraph

match: ["DocGraph", "doc graph"]
forbidden_synonyms: []
case_sensitive: true

The in-memory graph of all doc atoms in a repo, built from the docs tree for each
command that reads it (twice under `check --delta`, once per revision).

## Finding class

match: ["Finding class", "finding class", "finding classes"]
forbidden_synonyms: ["severity class", "Severity class"]
case_sensitive: true

How sure a finding is, which decides whether it blocks. A **certain** finding proves
the tree breaks a rule and is an error; a **hint** needs judgment and never errors; a
**time** finding comes from elapsed time or the outside world and is left out of a run
given a diff range.

## LanguageProfile

match: ["LanguageProfile", "LanguageProfiles"]
forbidden_synonyms: ["language pack", "Language pack", "language adapter", "Language adapter"]
case_sensitive: true

A bundle of source-root candidates and schema-leak regex patterns for one
programming language.

## RFC

match: ["RFC", "RFCs", "Request for Comments"]
forbidden_synonyms: ["proposal doc", "Proposal doc", "design proposal", "Design proposal"]
case_sensitive: true

A proposed feature or change in-flight, stored in `docs/rfcs/`
for review and feedback before final resolution.


## Specificity

match: ["Specificity", "specificity"]
forbidden_synonyms: []
case_sensitive: true

The ranking by which uniqueness picks the most-specific `describes` claim.
Fewer wildcards and more literal segments mean higher specificity.


## Anti-glossary

- Don't say *Linter*; Irminsul is a *checker*. Linters are line-level; Irminsul works at the graph level.
- Don't say *Documentation generator*; Irminsul *enforces structure*. It checks the docs tree and derives code surfaces on demand; it does not host or render a site.
