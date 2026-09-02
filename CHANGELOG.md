# Changelog

## Unreleased

### Enhancements
- `irminsul init --language <python|typescript|go|rust>` declares language profiles when code is not available for detection and may be repeated for multi-language projects. Interactive greenfield initialization prompts for at least one language; non-interactive initialization requires the option before writing a scaffold.
- `irminsul init --topology same-repo|siblings` — one command scaffolds either supported repository layout. `--topology siblings` takes `--code-repo <owner/repo|path>`, writes `source_roots` reaching through `../`, and generates two-checkout CI (ADR-0022).
- `claims[].evidence` now reads the same display spelling as `describes:`: repo-relative inside the docs repo, source-root-relative for files under a source root outside it. In the `siblings` layout a claim on `../code/src/core.py` is written `core.py`, so evidence and `describes:` can finally name the same file. Evidence that is absolute or reaches out through `..` is rejected. A spelling the source walk emits for a sibling file means that file even when the docs repo holds an unwalked file of the same name — the code repo's `README.md` under a widened root — so evidence and `describes:` never disagree about which file a spelling names.
- `globs` warns when one display path names two files — two configured roots outside the repo that both hold `a.py`, or a sibling file whose display is also the name of a docs-repo file the walk never visits, such as the docs repo's own `README.md`. The display encoding is not injective, so nothing downstream can disambiguate; the collision is now reported rather than resolved by luck.
- `irminsul context <path>` accepts the display spelling of a source file under a configured root outside the docs repo, so the `siblings` layout finally has a spelling for its own source files: with `source_roots = ["../code/src"]`, `irminsul context core.py` resolves, and `irminsul context ../code/src/core.py` maps that filesystem path to the same display spelling. A path outside the repo and outside every configured root is still refused.
- `irminsul init --topology siblings` offers the `irminsul seed` prompt again when interactive, the way every other path that scaffolds a brand-new project does.
- A check name that moved between `checks.hard` and `checks.soft_deterministic` is reported as moved, naming the list it belongs in, instead of as an unknown name.
- `--code-repo` reads a GitHub coordinate out of `https://github.com/owner/repo` and `git@github.com:owner/repo.git` as well as the `owner/repo` shorthand, and a `.git` suffix never reaches the checkout directory name. Windows separators are normalised, `~` is expanded, and a symlinked sibling keeps the name the user typed instead of being rewritten to its target. A trailing slash is stripped, and a value ending in `..` — `../..`, `code/..` — is rejected as a non-sibling instead of scaffolding `source_roots = ["../../src"]`.
- `--code-repo <bare-name>` is rejected instead of silently reinterpreted when a directory of that name already exists inside the docs repo, since the intended meaning is ambiguous.

### Changed
- **`retired-references` is now a hard check and its stale-guidance findings are errors**, so a reference to retired surface fails the gate without `--strict` (ADR-0022). Move it from `checks.soft_deterministic` to `checks.hard` in `irminsul.toml`. It now also audits ADRs (except against their own tombstones), the `AGENTS.md` / `CLAUDE.md` agent manifests, and frontmatter; the generated `regen agents-md` region and frozen RFC records stay out of range.
- `retired-references` concept phrases now fold case only when the declaration is written entirely in lower case ("smart case"). A capitalised declaration is a proper name and is matched case-sensitively, so a short one such as `Topology A` no longer matches the ordinary English "whatever topology a project picks". A tombstone that wants both readings lists both spellings in `matches`.
- `check --delta` inspects `docs_root` alongside `paths.source_roots` again when deciding whether it can answer. No supported layout puts the docs tree in its own repository, but a git submodule does, and `git worktree add` omits it from the base checkout exactly the way it omits a sibling code repo — so every pre-existing finding came back as new. The guard refuses instead, naming the offending tree.
- `retired-references` reads the `agents-manifest:generated-start` / `-end` markers only in the agent manifest that `regen agents-md` writes, skips fenced examples there, pairs a start and end written on one line, and blanks only a *balanced* pair; an unmatched start marker in the manifest is an error. An unclosed marker used to switch this hard check off for the rest of the file with nothing reported, and the marker text quoted anywhere else could either fail the build or hide stale guidance.
- `claim-provenance` no longer treats every path as source evidence when a configured source root is the repo root (`source_roots = ["."]`, what `irminsul init` writes for a flat Go repo). The docs tree, `irminsul.toml`, the Action and the CI workflows stay non-source, so `state: external` claims are satisfiable again and `implemented`/`available` claims are still checked.

### Removed
- The `lettered-topologies` tombstone from ADR-0022. It policed a naming convention rather than a removed surface — the layouts themselves are already tombstoned as `docs-only topology` — and the lettered names are gone from the tree.
- `/mkdocs.yml` from `.gitignore` — nothing has generated it since the render subsystem was retired (ADR-0013).
- `irminsul init-docs-only` and `irminsul init --fresh --topology docs-only`, along with the two nested repository layouts they served — code cloned into a gitignored subfolder of the docs repo, and `docs/` as a nested private repo inside the code repo (ADR-0022). Only `same-repo` and `siblings` are supported; moving to `siblings` is a filesystem move plus a `source_roots` edit, and nothing automates it.

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
