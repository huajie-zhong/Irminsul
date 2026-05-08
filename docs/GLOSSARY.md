# Glossary

Vocabulary used across Irminsul's codebase and docs. A single `GLOSSARY.md` is the authoritative dictionary for all domain terms.

Each entry should have:
- **Term** (singular, capitalized).
- **Definition** in one or two sentences.
- **Aliases** — informal synonyms used in the codebase.
- **Negative space** — what the term is NOT, when ambiguity exists.
- **Bounded context** — if the same word means different things in different parts of the system, scope it.
- **Since** — the version or PR where the term was introduced (optional).

CI enforces: any capitalized noun phrase used three or more times across the docs must have a glossary entry, OR be on the **anti-glossary** — a list of explicitly banned synonyms.

| Term | Definition | Aliases | Not to be confused with |
|------|------------|---------|-------------------------|
| **ADR** | The canonical, append-only record of a design decision and the reasoning ("why") behind it, stored in `docs/50-decisions/`. | Architecture Decision Record | an RFC (which is a proposal before a decision is finalized) |
| **Doc atom** | A single Markdown file with frontmatter. The smallest unit Irminsul tracks. | — | a doc *layer* (a directory like `20-components/`) |
| **DocGraph** | The in-memory graph of all doc atoms in a repo, built once per `irminsul check` invocation. | — | the rendered MkDocs site |
| **Hard check** | A blocking, deterministic check. Failure exits non-zero and fails CI. | blocking check | a soft check (advisory, doesn't fail CI) |
| **LanguageProfile** | A bundle of source-root candidates and schema-leak regex patterns for one programming language. | — | a doc tier |
| **RFC** | A proposed feature or change in-flight, stored in `docs/80-evolution/rfcs/` for review and feedback before final resolution. | Request for Comments, proposal | an ADR (the canonical record created once the RFC is accepted) |
| **Soft check** | An advisory check (deterministic or LLM-based). Emits findings but doesn't block. | advisory | a hard check |
| **Specificity** | The ranking by which uniqueness picks the most-specific `describes` claim. Fewer wildcards + more literal segments = higher specificity. | precedence | tier |
| **Tier** | The maintenance category of a doc atom (1 generated, 2 stable, 3 living, 4 ephemeral). | — | severity |

## Anti-glossary

- Don't say *Linter* — Irminsul is a *checker*. Linters are line-level; we work at the graph level.
- Don't say *Documentation generator* — Irminsul *enforces structure*; the renderer is one optional component.
