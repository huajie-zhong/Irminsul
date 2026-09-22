# AGENTS.md — agent entry point for Irminsul

This is the canonical guidance file for any coding agent working in this repository.
Harness-specific files at the repo root reference this one rather than restating it.

**Start at [`docs/AGENTS.md`](docs/AGENTS.md)** — the navigation manifest with the full
documentation tree, the doc-system rules, and the editing protocol. The mandatory work
order for lifecycle-bearing changes lives in
[`docs/guides/agent-protocol.md`](docs/guides/agent-protocol.md).

## The agent loop

1. At the start of a session, run `irminsul orient` and read `docs/AGENTS.md`.
2. Before editing, run `irminsul context --before-edit <path...>` for the files you
   intend to touch, or `irminsul context --topic <query>` while locating them. Then read
   the owning docs it names, and the decision records they link, before changing code.
   It runs no checks and validates nothing — its `validation` says `not_run` — so it is
   fast and it is not a green light.
3. Make the change. Keep doc updates **in the same commit** as the code they describe.
4. After editing, run `irminsul context --after-edit` to confirm ownership and surface
   any findings your edit introduced, and `irminsul list review --changed` to re-read every
   claim you added or changed against the code it names. Both also queue any claim whose
   evidence your change touched, whether or not you opened its document: read that
   document and the decisions it links, and answer the question asked.
   `--after-edit` reports two things and they answer different questions: the state of
   the whole repository, and what *this change* introduced against a baseline. On a
   branch whose work is already committed, pass `--base-ref origin/main` — otherwise the
   comparison has no baseline to use and says so rather than reporting a zero.
5. Run `irminsul fix` to apply deterministic remediations for mechanical findings.
6. Before committing, run `irminsul check` and the tests your change touches. It must
   exit 0. The pull request runs more than this — see below — and you do not need the
   whole gate on every local commit.
7. Before opening the pull request, run `irminsul check --diff origin/<base>`. That is
   the run CI enforces: it adds `co-change` and `diff-integrity`, which judge the change
   rather than the tree, and they are the ones that catch a weakened gate. `--diff HEAD`
   is not a substitute — HEAD already holds whatever this branch committed, so it
   compares the change with itself.

`context`, `check`, and friends support `--format json` for machine-readable output.

## Follow the foundation layer

The `foundation/` layer — principles, anti-patterns, and what the project will not do —
binds your choices, not just your prose. Follow it unless a principle is wrong for the
change at hand; then say so to the user and let them decide, rather than quietly working
around it. A principle you had to break is worth reporting even when the build is green.

## What a finding tells you

Every harness loads this file — Cursor and Codex read it natively, `CLAUDE.md` imports
it — so the posture lives here rather than in one harness's skill. The full procedure is
in [`docs/guides/agent-protocol.md`](docs/guides/agent-protocol.md).

- **A finding is right about its fact and silent about the meaning.** It reports
  something mechanical: this link resolves to nothing, this symbol is absent, no doc
  claims this file. Take that fact as true. Whether the prose is *correct* is what no
  check knows, so "the check is wrong" is almost never the answer.
- **A green run does not mean the docs are right.** It means nothing provable is broken.
- **A suggestion is a menu, not a ranking.** Several end "...or remove it", which is for
  when the thing really is gone — not a shortcut to clearing the finding.
- **When doc and code disagree, decide which is wrong before editing either.** A sentence
  describing what the code *should* do is a bug to report, not a doc to rewrite.

These clear a finding while making the tree less true, and none is a repair: deleting a
claim, anchor or `inventory:` entry; narrowing a `describes:` glob; setting `status:
draft`; an ignore comment as the first move or one without a real reason; re-running
`check --init-baseline`; editing an implemented RFC; re-pinning an anchor before
re-reading it; removing a check from `checks.enabled` or from the workflow; adding a path
to the [adoption record](docs/components/adoption-record.md), which names what was
already unowned on the day of adoption and only ever shrinks; deleting that record, or
adopting a second time, to get the first record's allowance back.

## What this project is

Irminsul is a Python CLI (`irminsul` / `irm`) plus composite GitHub Action (`action.yml`) that enforces structural invariants on a target codebase's `/docs` tree in CI. There is no server, no hosted state, and no LLM calls — every check is deterministic. Every invocation: load `irminsul.toml` → walk `docs_root` → build a `DocGraph` → run registered checks → exit 0/1 (2 for a config or usage error).

The repo dogfoods itself — `docs/` is the live spec for the doc system the tool enforces, and CI runs `irminsul check` against it.

## Common commands

Editable install with dev tooling (Python 3.12+ required):

```bash
pip install -e ".[dev]"      # ruff, mypy, pytest, pytest-cov, pre-commit
```

```powershell
.venv\Scripts\pytest -q          # run tests
.venv\Scripts\ruff check .       # lint
.venv\Scripts\mypy               # type-check
.venv\Scripts\irminsul check   # dogfood
```

Alternatively, `py -3.12 -m pytest` works if the uv venv is not activated, but `py -3.12 -m pip install -e ".[dev]"` must be run first. Name the version rather than trusting a bare `python`: which interpreter that is depends on PATH, and the project needs `>=3.12`.

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
irminsul check                             # the tree as it stands; run before every commit
irminsul check --diff origin/main          # what the pull request enforces; adds co-change
                                           # and diff-integrity
irminsul check --strict                    # also fail on hint and time findings
irminsul check --format json               # machine-readable output (CI parsers)
irminsul context --after-edit              # ownership, deps, and what this change introduced
irminsul list orphans                    # docs with no inbound refs
irminsul list stale                      # deprecated docs past stale threshold
irminsul list undocumented               # source files in covered dirs with no doc claim
irminsul list lifecycle                  # unfinished RFC lifecycle work
irminsul regen agents-md                 # rebuild the docs/AGENTS.md manifest
```

`pyproject.toml` sets `filterwarnings = ["error"]` for pytest — any warning fails the test. Don't suppress; fix the source.

## Architecture (the parts you need to read multiple files to understand)

**The single data structure: `DocGraph`** (`src/irminsul/docgraph.py`). Built once per CLI invocation by `build_graph(repo_root, config)`. Walks `docs_root`, parses every `*.md` (skipping the `EXEMPT_TOPLEVEL_NAMES` set: `README.md`, `GLOSSARY.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`), validates frontmatter, and exposes nodes by id and by repo-relative POSIX path. Every check consumes a `DocGraph`; nothing else. If you're adding behavior, ask first whether it belongs *on the graph* or *in a check*.

**One check registry, three finding classes** (`src/irminsul/checks/__init__.py`, `src/irminsul/checks/pipeline.py`). `checks.enabled` in `irminsul.toml` names the checks to run, resolved against `REGISTRY`; `config.py` rejects an unknown name at load time (exit 2) with a did-you-mean suggestion. Every finding code declares a class next to its explanation:
- **certain** — the tree provably breaks a rule; an error that fails every run, unless a baseline or `--delta` filters it out, or it sits on a draft doc *and* reports that doc as unfinished rather than as wrong about something outside it.
- **hint** — something may be wrong and needs judgment; a warning that fails a run only under `--strict`, or an info that never does. Investigate, then fix the doc or leave a reasoned `irminsul:ignore` comment.
- **time** — caused by elapsed time or the outside world; a warning left out of a run given `--diff`.

The registry in `checks/__init__.py` is the full list, and `irminsul orient` reports the enabled set live. This file deliberately carries neither the counts nor the names: nothing mechanical compares a hand-written list here against the registry, so it would go stale unseen.

All checks return `list[Finding]` with `(check, code, severity, path, line, message, suggestion)`. `pipeline.py` applies classes and ignore comments to every run; exit-code logic lives in `cli.check`.

**Cross-repo source files**. `walk_configured_source_files()` (`src/irminsul/checks/globs.py`) returns `(abs_path, display_posix)` pairs in its `files` — where `display_posix` is repo-relative for same-repo files but source-root-relative for files outside the docs repo. `src/irminsul/git/mtime.py` exposes `last_commit_time_any_repo()` which walks up from any absolute path to find its nearest `.git`, so `mtime-drift` works across sibling repos (the `siblings` layout). If a cross-repo source file has no `.git`, a Finding is emitted rather than silently skipping.

**`parent-child` check** infers parent–child relationships from document paths; there is no `children:` frontmatter field.

**Config** (`src/irminsul/config.py`). Pydantic schema for `irminsul.toml`. `find_config()` walks upward from the target path. Source-of-truth fields: `paths.docs_root`, `paths.source_roots`, `checks.enabled`, `languages.enabled`.

**Language profiles** (`src/irminsul/languages/`) are pure-data records (source-root candidates + schema-leak regexes) keyed by language name. Adding a language = adding a file here and registering it; config and checks read the registry, and only `init` auto-detection needs its own marker-file rule.

**Init scaffolder** (`src/irminsul/init/`) walks Jinja2 templates under `init/scaffolds/` and `init/workflows/` to bootstrap a new repo, then writes the agent-harness files (`.mcp.json`, merged into an existing registration under `--force`, and `.claude/skills/irminsul/SKILL.md`) from module constants; the root `AGENTS.md` router is a scaffold template, and the `CLAUDE.md` pointer is a module constant. Two layouts: `same-repo` (docs/ inside the code repo, the default) and `siblings` (`irminsul init --topology siblings --code-repo <spec>`, a docs repo beside a separate code repo). `detect_code_signals()` guards which one fits the target directory.

**`context`, `refs`, `new`, `regen`, and `list {orphans,stale,undocumented,lifecycle,review,baseline}`**. `irminsul context <path>|--topic <query>|--changed` (`src/irminsul/context.py`) returns ownership, tests, dependencies, relevant deterministic findings, and next command hints. `irminsul refs <doc-id|path>|--symbol <query>` (`src/irminsul/refs.py`) reports doc backlinks (strong `depends_on` plus weak markdown links) or symbol owners/references. `irminsul new {adr,component,rfc}` writes templated atoms from `src/irminsul/new/templates/`. `irminsul regen agents-md` (`src/irminsul/regen/agents_md.py`) is the only regen target — it rebuilds the `docs/AGENTS.md` navigation manifest. `irminsul list {orphans,stale,undocumented,lifecycle,baseline}` (`src/irminsul/listing/command.py`) wraps checks with custom filtering, and `list review` (`src/irminsul/listing/review.py`) queues assertion sentences for re-reading; each subcommand supports `--format plain|json`. The CLI also ships `seed` (PIB capture into the foundation layer), `surface` (derive cli/http/exports/env-var surfaces on demand), `anchors` (report or re-pin anchored prose claims), `mcp` (read-only MCP stdio server), and `fix` (deterministic remediations).

**The composite Action** (`action.yml`) is a thin shell wrapper: install the CLI (the pinned release when `version` is set, otherwise the same ref of this repository the workflow references) → `irminsul check --profile=… --format=…`. Don't add logic here; add it to the CLI and let the Action call it.

## The docs tree must obey the rules it enforces

`docs/` is the project's documentation, and because we ship a tool that enforces a doc system, our own docs must obey it too. CI dogfoods `irminsul check` against this repo, so a doc change that breaks the rules breaks the build. The six layers (`foundation/`, `architecture/`, `components/`, `decisions/`, `rfcs/`, `guides/`) are configured under `[layers]` in `irminsul.toml`; doc IDs are global bare slugs. `docs/CONTRIBUTING.md` is the authoritative authoring guide. Before adding or moving a doc, read `docs/architecture/layers.md`. If `irminsul check` fails on a doc change, the doc is wrong, not the check — fix the frontmatter, glob, or link rather than relaxing the check.

Note the two distinct files named `AGENTS.md`: **this file** is the root harness router, and `docs/AGENTS.md` is the generated navigation manifest. Root-level files sit outside `docs_root`, so most doc-graph checks cannot see them; `links`, `retired-references`, `code-references`, ignore comments, and `irminsul list review` read the files named by `paths.extra_docs` (the readme and the two agent files by default). Their accuracy is otherwise a review responsibility.

## Tests

Fixture repos under `tests/fixtures/repos/<scenario>/` are full miniature codebases (their own `irminsul.toml`, `docs/`, sometimes `app/`). Each scenario is named for what it exercises — `bad-frontmatter/`, `bad-uniqueness/`, `soft-orphans/`, `good/`, etc. When adding a check, add a fixture repo demonstrating both the failure and (where applicable) the green case; don't try to construct `DocGraph`s by hand in tests. `tests/conftest.py` provides the wiring.

CI matrix: ubuntu/macos/windows × Python 3.12/3.13. Code that touches paths must use `pathlib` and POSIX-normalize (see `_to_repo_relative` in `docgraph.py`) — Windows-only path bugs will only surface in CI.

## Versioning and release

Version is driven by `hatch-vcs` from git tags; the wheel writes `src/irminsul/_version.py` at build time. Don't hand-edit version strings. Release flow lives in `.github/workflows/release.yml` (builds wheel + sdist, idempotent PyPI publish, ghcr.io Docker image, and a Homebrew tap dispatch that needs the `HOMEBREW_TAP_TOKEN` secret). <!-- irminsul:ignore code-references/unknown-env-var reason="a CI secret the release workflow reads, not this code" -->

## Harness notes

Cursor and Codex read a root `AGENTS.md` natively. Claude Code reads `CLAUDE.md`, so this
repo's `CLAUDE.md` references this file with `@AGENTS.md` rather than duplicating it,
because a duplicate of guidance would drift unseen: no check compares the two copies.

`.mcp.json` at the repo root registers Irminsul's read-only MCP server, which exposes the
orientation, context, refs, check, list, surface, anchors, and change queries as tools. The
harness runs the `irminsul` on its own PATH, not the one in `.venv`, and that install needs
the optional extra (`pip install 'irminsul[mcp]'`, already in `[dev]`). Without it the harness
reports only a closed connection.

Two different failures produce that same closed connection, and only one of them can
explain itself. If `irminsul` starts but lacks the extra, running it prints the install
hint. If the `irminsul` on PATH is a console script left behind by an uninstalled
package, it dies inside its own `__main__` before any Irminsul code runs, so running it
prints a `ModuleNotFoundError` traceback and no hint — and asking it to diagnose itself is
circular. Diagnose that one without the script: `python -c "import irminsul,
irminsul.mcp_server"`. Repair it with `pipx install --force irminsul`, or
`python -m pip install --force-reinstall 'irminsul[mcp]'` into the interpreter on PATH,
deleting the stale script first. `irminsul init` now tries the launcher and says so.
