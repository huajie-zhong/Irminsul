---
id: ci-runs-each-gate-once-and-the-action-takes-typed-inputs
title: "CI runs each gate once, and the Action takes typed inputs"
status: stable
describes: []
summary: CI installs from the lock, runs the self-check once per event with hints failing, tests four legs with a coverage floor on one, and installs the built wheel; the Action takes typed inputs only.
governs:
  - .github/workflows/**
  - action.yml
  - Dockerfile
  - .pre-commit-config.yaml
  - src/irminsul/init/workflows/**
  - src/irminsul/init/command.py#action_ref
  - src/irminsul/init/command.py#_ACTION_REPOSITORY
---

# CI runs each gate once, and the Action takes typed inputs

## Status

Accepted, 2026-10-28.

## Context

A gate run twice prints each finding twice, and one that passes on a hint contradicts the rule
this repository ships, that a hint needs an answer. Tools installed without a lock run versions
nobody tested, and only installing the built wheel on a clean machine notices a wheel missing a
template or a dependency. An Action varied by free-form text expanded into a command line is an
injection point with no list of the flags it supports.

## Decision

- **The jobs that install the dev tools run `uv sync --locked --extra dev`** after
  `astral-sh/setup-uv`, and the tools with `uv run`, in `.github/workflows/ci.yml` and the `verify` job of
  `.github/workflows/release.yml`; a stale `uv.lock` fails the job. The ruff and mypy
  pre-commit hooks are `repo: local` hooks through `uv run`, and mypy checks the whole source
  tree whenever a file under `src/` is staged.
- **`lint`** holds `ruff check`, `ruff format --check` and `mypy`.
- **Four test legs:** ubuntu on 3.12 and 3.13, windows and macos on 3.12. Coverage is measured
  on ubuntu 3.12 alone, with the hand-set floor `--cov-fail-under=94`.
- **`dogfood` runs each gate once, failing on hints.** A pull request or merge queue runs
  `irminsul check --diff "origin/<base>" --fail-on hint`, which reports what a plain run does
  plus the change passes; a push to `main` runs `irminsul check --fail-on hint`. Time findings
  fail nothing here.
- **`action`** runs the Action on this repository and with `path: tests/fixtures/repos/good`.
- **`package` installs what a user installs:** it builds with `uv build`, installs the wheel
  alone into a fresh virtualenv with dependencies resolved fresh, runs `irminsul --version`, and
  in an empty directory `git init`, `irminsul init --fresh --no-interactive --language python`
  and `irminsul check`, then builds and runs the image from that wheel.
- **`.github/workflows/ci.yml` declares `permissions: contents: read`.**
- **The Action takes typed inputs only:** `fail-on`, `format` (default `github`), `diff`, `path`
  (`--path`), `source-diff` (`--source-diff`) and `version`, each reaching the shell through
  `env`, never expanded into script source.
- **Every workflow `init` writes calls the Action**, the `siblings` ones with `path` naming the
  docs checkout, and none installs the CLI by hand. `action_ref()` is the one pin `init`
  computes, `@main` for a development build. A test holds the inputs each scaffolded workflow
  passes to those `action.yml` declares, because GitHub runs a step without an undeclared input
  and only warns.
- **The workflows `init` writes have no `paths:` filter,** which would leave a required check
  pending on a pull request it skips.

## Alternatives Considered

- **A plain run beside `--diff` on pull requests.** Rejected: it reports a subset, twice.
- **Fail on time findings.** Rejected: the calendar would turn `main` red with no change; a
  scheduled run is their place.
- **Windows and macos on 3.13.** Rejected: they repeat what the other legs run, at a higher
  price per minute.
- **A coverage floor on every leg.** Rejected: each platform skips different tests.
- **Hand-written install steps in the `siblings` workflows.** Rejected: three copies of one
  step, each pinned by code that existed only to pin them.
- **A free-form `args` input.** Rejected: an injection point with no list of supported flags.
- **Choosing `--path` or the format from `GITHUB_ACTIONS` in the CLI.** Rejected: local and CI
  runs would differ invisibly.
- **A `paths:` filter that also lists `test_roots`.** Rejected: one omission makes a pull
  request unmergeable.

## Consequences

- The checks to require in branch protection are those
  [enforcement](../foundation/enforcement.md#what-the-workflow-cannot-enforce) lists: `lint`, the
  four `test (...)` legs, `dogfood`, `action` and `package`.
- A hint on `main` is a red build. A failure only windows or macos on 3.13 would show goes
  unfound. The coverage floor rises only when someone raises it.
- The lock has to pass the suite, which may need newer versions than `pyproject.toml`
  requires: the suite needs `mcp` 2.1, while the server runs on the 2.0 floor.
- A `siblings` run's annotations name files relative to `path`, so GitHub shows them on the run
  without attaching them to a file.
