# Irminsul

> A documentation system for complex codebases. Designed to resist rot, scale with complexity, and survive philosophy shifts.

Irminsul is a Python CLI + composite GitHub Action that enforces structural invariants on your `/docs` tree in CI. The rules are simple: every fact has one home, every doc has one purpose, every cross-reference is bidirectional and machine-verifiable. The tool's job is to make sure those rules stay true while the codebase evolves.

## Quickstart

```bash
pipx install irminsul
cd my-codebase
irminsul init
```

That scaffolds a 9-layer `/docs` skeleton, an `irminsul.toml` config, GitHub Actions workflows, and pre-commit hooks. Three commands, ten seconds, fully wired.

## What it checks

Hard, blocking checks (deterministic, no LLM):

- **Frontmatter validity** — required fields present, enums valid, IDs match filenames
- **Glob resolution** — every `describes` glob resolves to ≥1 source file
- **Coverage uniqueness** — every source file is claimed by exactly one most-specific doc
- **Internal link integrity** — no broken `[link](other.md)` references
- **Schema-leak detection** — no class/type definitions in component docs (those belong in the generated reference layer)

Coming in Sprint 2: mtime drift, orphan detection, supersession auto-update, parent-child consistency, glossary linter, and LLM-advisory checks for behavioral overlap and semantic drift.

## CI integration

```yaml
on: pull_request
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: anson/irminsul@v0.1.0
        with:
          scope: hard
```

`irminsul init` writes this file for you.

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE).

## Reference

The full architectural reference for the doc system Irminsul enforces lives in [`Irminsul-reference.md`](Irminsul-reference.md).
