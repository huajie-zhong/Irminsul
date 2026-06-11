---
id: checks
title: Checks
audience: explanation
tier: 3
status: stable
depends_on:
  - config
  - docgraph
  - frontmatter
  - init
  - languages
  - llm
  - new-list-regen
describes:
  - src/irminsul/checks/**
tests:
  - tests/test_checks_frontmatter.py
  - tests/test_checks_globs.py
  - tests/test_checks_links.py
  - tests/test_checks_schema_leak.py
  - tests/test_checks_uniqueness.py
  - tests/test_checks_coverage.py
  - tests/test_checks_liar.py
  - tests/test_checks_reality.py
  - tests/test_checks_boundary.py
  - tests/test_checks_doc_reality.py
---

# Checks

Checks consume a [DocGraph](docgraph.md) and return `Finding` records with severity, message, and a path/line where applicable. The exact registry surface is defined by the Python registries in `src/irminsul/checks/__init__.py`.

| Example check | What it enforces | Severity |
|---------------|------------------|----------|
| `frontmatter` | Required fields present, enums valid, id matches filename rule, no duplicate ids | error |
| `globs` | Every `describes` pattern resolves to ≥1 source file | error |
| `uniqueness` | Each source file claimed by exactly one most-specific doc; ties are silent duplication | error / warning |
| `links` | Internal markdown links resolve; external/anchor-only skipped | error |
| `schema-leak` | No type/schema definitions inside `docs/20-components/` (they live in code, not docs) | error |
| `prose-file-reference` | Local `.md` references in prose must be real links or explicitly ignored | error |

Soft deterministic checks warn rather than block. For example, `foundation-readiness` warns when a `00-foundation/` or `10-architecture/` doc still contains literal scaffold placeholder phrases — a signal the project never ran [`irminsul seed`](seed.md) to capture real intent.

One enforcement lives outside the registries: `co-change`. It needs a changed-file set from git, so it runs only when the [CLI](cli.md) is given `--diff <base>` (or the equivalent two-flag spelling `--base-ref`/`--head-ref`; the two forms are mutually exclusive). It is the only diff-precise signal — `mtime-drift` no longer carries one. Each source file changed in `<base>...HEAD` is resolved to its most-specific owning docs through the same `describes` glob logic as `uniqueness`; when none of a file's owning docs changed in the same diff, each owning doc gets one warning listing its changed-but-unreflected files. `--strict` promotes the warning to an error, like the soft deterministic set.

Checks are registered in `HARD_REGISTRY`, `SOFT_REGISTRY`, and `LLM_REGISTRY` keyed by name. The CLI selects checks with `--profile`: `hard` runs configured hard checks, `configured` adds configured soft deterministic checks, `advisory` adds configured LLM checks, and `all-available` runs every implemented deterministic check regardless of config.

## Scope & Limitations

Checks do not apply fixes — findings are advisory output only; call `irminsul fix` to remediate. They do not evaluate prose quality or writing style. They do not modify source files or docs.
