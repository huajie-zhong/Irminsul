# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Irminsul is a Python CLI (`irminsul` / `irm`) plus composite GitHub Action (`action.yml`) that enforces structural invariants on a target codebase's `/docs` tree in CI. There is no server, no hosted state, and no LLM calls — every check is deterministic. Every invocation: load `irminsul.toml` → walk `docs_root` → build a `DocGraph` → run registered checks → exit 0/1.

The repo dogfoods itself — `docs/` is the live spec for the doc system the tool enforces, and CI runs `irminsul check --profile=hard` against it.

## Common commands

Editable install with dev tooling (Python 3.12+ required):

```bash
pip install -e ".[dev]"      # ruff, mypy, pytest, pytest-cov, pre-commit
```

```powershell
.venv\Scripts\pytest -q          # run tests
.venv\Scripts\ruff check .       # lint
.venv\Scripts\mypy               # type-check
.venv\Scripts\irminsul check --profile=hard   # dogfood
```

Alternatively, `py -3.12 -m pytest` works if the uv venv is not activated, but `py -3.12 -m pip install -e ".[dev]"` must be run first. The system `python` on this machine is 3.10 and will not satisfy the `>=3.12` requirement.

Day-to-day:

```bash
pytest -q                                          # full suite
pytest tests/test_checks_uniqueness.py -q          # one file
pytest -k uniqueness -q                            # by keyword
pytest -q --cov=irminsul --cov-report=term-missing # what CI runs
ruff check . && ruff format --check .              # lint + format gate
mypy                                               # strict, src/irminsul only
```

Self-check (dogfood) — must pass before merging:

```bash
irminsul check --profile=hard              # the gate CI enforces on this repo
irminsul check --profile=configured        # hard + configured soft deterministic
irminsul check --profile=hard --format json  # machine-readable output (CI parsers)
irminsul context --changed                 # ownership, tests, deps, and findings for current edits
irminsul list orphans                    # docs with no inbound refs
irminsul list stale                      # deprecated docs past stale threshold
irminsul list undocumented               # source files in covered dirs with no doc claim
irminsul list lifecycle                  # unfinished decision update work
irminsul regen agents-md                 # rebuild the docs/AGENTS.md manifest
```

`pyproject.toml` sets `filterwarnings = ["error"]` for pytest — any warning fails the test. Don't suppress; fix the source.

## Architecture (the parts you need to read multiple files to understand)

**The single data structure: `DocGraph`** (`src/irminsul/docgraph.py`). Built once per CLI invocation by `build_graph(repo_root, config)`. Walks `docs_root`, parses every `*.md` (skipping the `EXEMPT_TOPLEVEL_NAMES` set: `README.md`, `GLOSSARY.md`, `CONTRIBUTING.md`, `AGENTS.md`), validates frontmatter, and exposes nodes by id and by repo-relative POSIX path. Every check consumes a `DocGraph`; nothing else. If you're adding behavior, ask first whether it belongs *on the graph* or *in a check*.

**Two check registries** (`src/irminsul/checks/__init__.py`). Names in `irminsul.toml` are resolved against these maps. `config.py` validates `checks.hard`/`checks.soft_deterministic` against its own known-name tuples at config-load time — an unknown name is a hard error (red message with a did-you-mean suggestion, exit 2), not a skip.
- `HARD_REGISTRY` — 9 checks: `frontmatter`, `globs`, `uniqueness`, `links`, `schema-leak`, `coverage`, `liar`, `prose-file-reference`, `agents-manifest`. Errors from these always block (exit 1) regardless of `--strict`.
- `SOFT_REGISTRY` — 19 deterministic warnings: `mtime-drift`, `orphans`, `stale-reaper`, `supersession`, `parent-child`, `glossary-discipline`, `external-links`, `rfc-resolution`, `reality`, `claim-anchor`, … (full list in `checks/__init__.py`). Promoted to errors only with `--strict`.

All checks subclass `Check` and return `list[Finding]` with `(check, severity, path, line, message, suggestion)`. Severity ordering and exit-code logic live in `cli.check`.

**Cross-repo source files**. `walk_source_files()` (`src/irminsul/checks/globs.py`) returns `list[tuple[Path, str]]` — `(abs_path, display_posix)` — where `display_posix` is repo-relative for same-repo files but source-root-relative for files outside the docs repo. `src/irminsul/git/mtime.py` exposes `last_commit_time_any_repo()` which walks up from any absolute path to find its nearest `.git`, so `mtime-drift` works across sibling repos (Topology A/B). If a cross-repo source file has no `.git`, a Finding is emitted rather than silently skipping.

**`parent-child` check** infers parent–child relationships from document paths; there is no `children:` frontmatter field.

**Config** (`src/irminsul/config.py`). Pydantic schema for `irminsul.toml`. `find_config()` walks upward from the target path. Source-of-truth fields: `paths.docs_root`, `paths.source_roots`, `checks.hard|soft_deterministic`, `languages.enabled`.

**Language profiles** (`src/irminsul/languages/`) are pure-data records (source-root candidates + schema-leak regexes) keyed by language name. Adding a language = adding a file here, no check changes.

**Init scaffolder** (`src/irminsul/init/`) walks Jinja2 templates under `init/scaffolds/` and `init/workflows/` to bootstrap a new repo. Two modes: `init` (single-repo, the common case) and `init-docs-only` (Topology A: docs repo + sibling code repo cloned as gitignored subfolder). `detect_code_signals()` decides which to suggest.

**`context`, `refs`, `new`, `regen`, and `list`**. `irminsul context <path>|--topic <query>|--changed` (`src/irminsul/context.py`) returns ownership, tests, dependencies, relevant deterministic findings, and next command hints. `irminsul refs <doc-id|path>|--symbol <query>` (`src/irminsul/refs.py`) reports doc backlinks (strong `depends_on` plus weak markdown links) or symbol owners/references. `irminsul new {adr,component,rfc}` writes templated atoms from `src/irminsul/new/templates/`. `irminsul regen agents-md` (`src/irminsul/regen/agents_md.py`) is the only regen target — it rebuilds the `docs/AGENTS.md` navigation manifest. `irminsul list {orphans,stale,undocumented,lifecycle}` (`src/irminsul/listing/command.py`) wraps checks with custom filtering; each subcommand supports `--format plain|json`. The CLI also ships `seed` (PIB capture into the foundation layer), `surface` (derive cli/http/exports/env-var surfaces on demand), `anchors` (report or re-pin anchored prose claims), and `fix` (deterministic remediations).

**The composite Action** (`action.yml`) is a thin shell wrapper: `pip install irminsul[==version]` → `irminsul check --profile=…`. Don't add logic here; add it to the CLI and let the Action call it.

## The docs tree must obey the rules it enforces

`docs/` is the project's documentation, and because we ship a tool that enforces a doc system, our own docs must obey it too. CI dogfoods `irminsul check --profile=hard` against this repo, so a doc change that breaks the rules breaks the build. The 9-layer structure (`00-foundation/`, `10-architecture/`, …, `90-meta/`) is enforced; doc IDs use bare slugs because the numeric prefixes namespace them. `docs/CONTRIBUTING.md` is the authoritative authoring guide. Before adding or moving a doc, read `docs/10-architecture/layers.md` and `docs/10-architecture/tiers.md`. If `irminsul check --profile=hard` fails on a doc change, the doc is wrong, not the check — fix the frontmatter, glob, or link rather than relaxing the check.

## Tests

Fixture repos under `tests/fixtures/repos/<scenario>/` are full miniature codebases (their own `irminsul.toml`, `docs/`, sometimes `app/`). Each scenario is named for what it exercises — `bad-frontmatter/`, `bad-uniqueness/`, `soft-orphans/`, `good/`, etc. When adding a check, add a fixture repo demonstrating both the failure and (where applicable) the green case; don't try to construct `DocGraph`s by hand in tests. `tests/conftest.py` provides the wiring.

CI matrix: ubuntu/macos/windows × Python 3.12/3.13. Code that touches paths must use `pathlib` and POSIX-normalize (see `_to_repo_relative` in `docgraph.py`) — Windows-only path bugs will only surface in CI.

## Versioning and release

Version is driven by `hatch-vcs` from git tags; the wheel writes `src/irminsul/_version.py` at build time. Don't hand-edit version strings. Release flow lives in `.github/workflows/release.yml` (builds wheel + sdist, idempotent PyPI publish, ghcr.io Docker image, and a Homebrew tap dispatch that needs the `HOMEBREW_TAP_TOKEN` secret).
