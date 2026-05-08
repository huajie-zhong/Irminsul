# Glossary

Vocabulary used across Irminsul's codebase and docs.

| Term | Definition | Aliases | Not to be confused with |
|------|------------|---------|-------------------------|
| **Doc atom** | A single Markdown file with frontmatter. The smallest unit Irminsul tracks. | — | a doc *layer* (a directory like `20-components/`) |
| **DocGraph** | The in-memory graph of all doc atoms in a repo, built once per `irminsul check` invocation. | — | the rendered MkDocs site |
| **Hard check** | A blocking, deterministic check. Failure exits non-zero and fails CI. | blocking check | a soft check (advisory, doesn't fail CI) |
| **Soft check** | An advisory check (deterministic or LLM-based). Emits findings but doesn't block. | advisory | a hard check |
| **LanguageProfile** | A bundle of source-root candidates and schema-leak regex patterns for one programming language. | — | a doc tier |
| **Specificity** | The ranking by which uniqueness picks the most-specific `describes` claim. Fewer wildcards + more literal segments = higher specificity. | precedence | tier |
| **Tier** | The maintenance category of a doc atom (1 generated, 2 stable, 3 living, 4 ephemeral). | — | severity |

## Anti-glossary

- Don't say *Linter* — Irminsul is a *checker*. Linters are line-level; we work at the graph level.
- Don't say *Documentation generator* — Irminsul *enforces structure*; the renderer is one optional component.
