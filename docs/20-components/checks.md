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
  - tests/test_checks_adr_structure.py
  - tests/test_checks_rfc_lifecycle_integrity.py
  - tests/test_walk_source_files.py
implements:
  - 0023-adr-template-structure
  - 0035-rfc-lifecycle-integrity-and-frozen-records
---

# Checks

Checks consume a [DocGraph](docgraph.md) and return `Finding` records with severity, message, and a path/line where applicable. The exact registry surface is defined by the Python registries in `src/irminsul/checks/__init__.py`.

| Example check | What it enforces | Severity |
|---------------|------------------|----------|
| `frontmatter` | Required fields present, enums valid, id matches filename rule, no duplicate ids | error |
| `globs` | Every `describes` pattern resolves under the configured source policy; unsafe symlink escapes are rejected | error / warning |
| `uniqueness` | Each source file claimed by exactly one most-specific doc; ties are silent duplication | error / warning |
| `links` | Internal markdown links resolve; external/anchor-only skipped | error |
| `schema-leak` | No type/schema definitions inside `docs/20-components/` (they live in code, not docs) | error |
| `prose-file-reference` | Local `.md` references in prose must be real links or explicitly ignored | error |
| `rfc-lifecycle-integrity` | Implemented RFC seals, premature implementation evidence, and draft/live lifecycle drift | error / warning |

Soft deterministic checks warn rather than block. For example, `foundation-readiness` warns when a `00-foundation/` or `10-architecture/` doc still contains literal scaffold placeholder phrases — a signal the project never ran [`irminsul seed`](seed.md) to capture real intent. Another, `doc-refs`, warns when a `depends_on` entry names a doc id that doesn't exist in the graph — a dangling edge would otherwise silently weaken orphan detection and the other consumers of strong dependencies; the [refs query](refs.md) helps locate the intended doc. A third, `phantom-layer`, flags a directory whose only doc is its INDEX as navigation rot — at `warning` when that INDEX is `status: stable`, downgraded to `info` when it is `status: draft`, since a draft INDEX marks a layer deliberately under construction (the state every freshly scaffolded layer starts in) rather than abandoned navigation. And `change-binding` keeps declared change intent honest: an accepted RFC must declare `affects` explicitly, every declared component id must resolve, and when a diff range is available the declared scope is compared against the components that actually own the changed source (see the [change lifecycle](change.md)). `requirement-grammar` validates the requirement/scenario structure of behavior-changing RFCs — stable unique ids, SHALL/MUST behavior text, WHEN/THEN scenarios, a supported evidence class, or the explicit no-new-behavior disposition; the same findings that warn here block `change transition ... accepted`, because acceptance freezes the contract to implement.

`adr-structure` keeps architecture decision records reviewable by warning on missing or duplicate canonical sections and on an empty or placeholder-only `## Decision`. It is a shape check, not a lifecycle engine: RFC state remains in structured lifecycle metadata, and the check does not interpret an ADR's human-readable `## Status` prose.

The generic `supersession` check maintains reciprocal `supersedes` / `superseded_by`
metadata for ordinary documents. RFC records are excluded from that repair path:
their replacement graph is forward-only from the successor's `supersedes`, and
reverse successors are derived by [`change graph`](change.md). This prevents a new
proposal from demanding a metadata write to an implemented, sealed predecessor.

`prose-file-reference` also audits its own exception markers as specified by
[RFC 0039](../80-evolution/rfcs/0039-stale-prose-suppressions.md). A line marker
is active only when its line still contains an unlinked local `.md` reference
after the marker comment is removed. A matched block is active only when an
enclosed, non-fenced line would independently trigger the check. Clean markers
produce one `info` finding with `category: stale-suppression` and structured
line-or-block scope. Informational findings are not stored in baselines, so a
baseline update cannot hide obsolete exceptions. Unmatched block markers remain
hard errors, and marker removal stays manual.

One enforcement lives outside the registries: `co-change`. It needs a changed-file set from git, so it runs only when the [CLI](cli.md) is given `--diff <base>` (or the equivalent two-flag spelling `--base-ref`/`--head-ref`; the two forms are mutually exclusive). It is the only diff-precise signal — `mtime-drift` no longer carries one. Each source file changed in `<base>...HEAD` is resolved to its most-specific owning docs through the same `describes` glob logic as `uniqueness`; when none of a file's owning docs changed in the same diff, each owning doc gets one warning listing its changed-but-unreflected files. `--strict` promotes the warning to an error, like the soft deterministic set.

Checks are registered in `HARD_REGISTRY` and `SOFT_REGISTRY` keyed by name. The CLI selects checks with `--profile`: `hard` runs configured hard checks, `configured` adds configured soft deterministic checks, and `all-available` runs every implemented deterministic check regardless of config.

In JSON output (`--format json`) every finding carries two machine-actionable fields for agents. `data` is a structured decomposition of the finding — always with a kebab-case `problem` key and string values — or `null` where no decomposition exists; the `frontmatter`, `coverage`, and `links` checks populate it. `fixable` is `true` exactly when `irminsul fix` would plan a remediation for *that* finding, in which case the finding also carries a ready-to-run `fix_command`.

Both halves of that claim are load-bearing, and each constrains an implementation detail. Because `irminsul fix --check` only selects checks active under *its own* profile, the emitted `fix_command` repeats the profile the finding was reported under (`irminsul fix --profile all-available --check supersession`) — otherwise a finding surfaced by `--profile all-available` would advertise a command that silently no-ops under `fix`'s default `configured` profile. And because some remediations are `requires_confirm` (they rewrite load-bearing metadata or prose), the command appends `--confirm` when any of the fixes it would plan is held back without it. Fixability is also per *finding*, not per doc: a check's `fixes()` discriminates on the finding's category, so an unfixable finding (a dangling `resolved_by`, a missing reverse `supersedes` pointer) stays `fixable: false` even when the same doc carries a fixable finding of another category.

## RFC lifecycle integrity

`rfc-lifecycle-integrity` is a hard-profile check with mixed severity
([RFC 0035](../80-evolution/rfcs/0035-rfc-lifecycle-integrity-and-frozen-records.md)).
It errors when a sealed implemented RFC changes, a non-implemented RFC carries a
seal, or an `implements:` backlink contradicts the RFC state. Missing seals on
legacy implemented RFCs and stable live docs linking draft RFCs are warnings so
repositories can migrate without weakening actual freeze violations.

## Source inventory and glob resolution

The shared source walker applies built-in noise exclusions, repository-local `.gitignore`, and configured include/exclude patterns before any check or report sees a file. Directory symlinks are not traversed. A file symlink is inventoried under its lexical path only when its resolved target remains within the resolved configured source root; an escaping target is an error, while a broken target is a warning. Explicit external or symlinked source roots remain supported because the configured root itself defines the containment boundary.

## Scope & Limitations

Checks do not apply fixes — findings are advisory output only; call `irminsul fix` to remediate. They do not evaluate prose quality or writing style. They do not modify source files or docs, and source discovery never follows directory symlinks.
