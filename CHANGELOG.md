# Changelog

## v0.2.0 (2026-05-08)

### New checks (hard)
- **rfc-lifecycle-integrity** — freezes implemented RFC records with an enforced SHA-256 seal and detects lifecycle-state contradictions

### New checks (soft-deterministic)
- **mtime-drift** — warns when source files were committed more recently than `last_reviewed`
- **orphans** — warns when a doc has no inbound references (not linked, not in a parent's `children:`)
- **stale-reaper** — warns when a `deprecated` doc is older than the configured threshold
- **supersession** — checks reciprocity of `supersedes` / `superseded_by` pairs
- **parent-child** — validates `INDEX.md` `children:` against on-disk siblings; bans wildcard `describes` on parent docs with real children
- **glossary** — warns when a doc redefines a term that belongs in `GLOSSARY.md`
- **external-links** — HEAD-checks external URLs with a persistent disk cache (disabled by default; enable in nightly CI)

### New commands
- `irminsul new adr <title>` — scaffold an ADR in `docs/50-decisions/`
- `irminsul new component <name>` — scaffold a component doc in `docs/20-components/`
- `irminsul new rfc <title>` — scaffold an RFC in `docs/80-evolution/rfcs/`
- `irminsul list orphans` — list docs with no inbound references
- `irminsul list stale` — list deprecated docs past the stale threshold
- `irminsul list undocumented` — list source files in covered dirs that no doc claims
- `irminsul context <path>|--topic <query>|--changed` — return task-specific ownership, dependency, test, and finding context
- `irminsul regen agents-md` — regenerate the `docs/AGENTS.md` agent navigation manifest
- `irminsul surface <kind>` — derive a code surface (cli, http, exports, env-vars) on demand, written nowhere
- `irminsul init-docs-only --code-repo <spec>` — scaffold a docs-only repo where code lives in a separate GitHub repo (Topology A)

### Enhancements
- `irminsul change finalize` seals the implemented RFC after its lifecycle edits
- `irminsul list lifecycle --queue` includes freeze violations and draft/live state drift
- `irminsul check --profile=hard|configured|all-available` — explicit check profiles replace `--scope`
- `irminsul fix --profile=hard|configured|all-available` — fix selection now uses the same profile vocabulary
- `irminsul check --strict` — promote warnings to errors for exit code
- Go and Rust language profiles added to `LANGUAGE_REGISTRY`
- Anchor validation in `LinksCheck` (same-doc `#heading` and cross-doc `file.md#heading`)
- `SchemaLeakCheck` protected paths now configurable via `[checks.schema_leak] protected_paths`
- `Finding` gains `suggestion` and `category` fields; suggestions printed as dim `→` hints

### Fixes
- `irminsul init` now errors clearly when run in a directory with no code signals and `--no-interactive`

### Removed
- The render subsystem — `irminsul render`, `regen python`/`typescript`, the `[render]`/`[regen]` config, and the `[mkdocs]` extra (ADR-0013). Derivable reference is obtained on demand via `irminsul surface`.
- Tier 1 ("Generated") and the `40-reference/` layer, plus the `[tiers].generated` config field (ADR-0014). `tier:` frontmatter now accepts 2–4; non-derivable reference lives in its owning layer.
- The `[llm]` config table and `checks.soft_llm` — accepted by the v0.1.0 schema but never backed by a working check. The config schema now rejects both; remove them from `irminsul.toml`. Every check is deterministic.

## v0.1.0

Initial release. Five hard checks (frontmatter, globs, uniqueness, links, schema-leak),
`irminsul init`, `irminsul render` (MkDocs Material), composite GitHub Action, Dockerfile,
PyPI + Homebrew + ghcr.io release pipeline.
