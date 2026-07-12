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
  - tests/test_checks_doc_refs.py
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

Soft deterministic checks warn rather than block. For example, `foundation-readiness` warns when a `00-foundation/` or `10-architecture/` doc still contains literal scaffold placeholder phrases — a signal the project never ran [`irminsul seed`](seed.md) to capture real intent. Another, `doc-refs`, warns when a `depends_on` entry names a doc id that doesn't exist in the graph — a dangling edge would otherwise silently weaken orphan detection and the other consumers of strong dependencies; the [refs query](refs.md) helps locate the intended doc.

Checks are registered in `HARD_REGISTRY`, `SOFT_REGISTRY`, and `LLM_REGISTRY` keyed by name. The CLI selects checks with `--profile`: `hard` runs configured hard checks, `configured` adds configured soft deterministic checks, `advisory` adds configured LLM checks, and `all-available` runs every implemented deterministic check regardless of config.

In JSON output (`--format json`) every finding carries two machine-actionable fields for agents. `data` is a structured decomposition of the finding — always with a kebab-case `problem` key and string values — or `null` where no decomposition exists; the `frontmatter`, `coverage`, and `links` checks populate it. `fixable` is `true` exactly when `irminsul fix` would plan a remediation for *that* finding, in which case the finding also carries a ready-to-run `fix_command`.

Both halves of that claim are load-bearing, and each constrains an implementation detail. Because `irminsul fix --check` only selects checks active under *its own* profile, the emitted `fix_command` repeats the profile the finding was reported under (`irminsul fix --profile all-available --check supersession`) — otherwise a finding surfaced by `--profile all-available` would advertise a command that silently no-ops under `fix`'s default `configured` profile. And because some remediations are `requires_confirm` (they rewrite load-bearing metadata or prose), the command appends `--confirm` when any of the fixes it would plan is held back without it. Fixability is also per *finding*, not per doc: a check's `fixes()` discriminates on the finding's category, so an unfixable finding (a dangling `resolved_by`, a missing reverse `supersedes` pointer) stays `fixable: false` even when the same doc carries a fixable finding of another category.

## Scope & Limitations

Checks do not apply fixes — findings are advisory output only; call `irminsul fix` to remediate. They do not evaluate prose quality or writing style. They do not modify source files or docs.
