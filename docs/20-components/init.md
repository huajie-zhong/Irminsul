---
id: init
title: Init scaffolder
audience: explanation
tier: 3
status: stable
depends_on:
  - languages
describes:
  - src/irminsul/init/**
tests:
  - tests/test_init.py
  - tests/test_init_detector.py
  - tests/test_init_docs_only.py
implements:
  - 0035-rfc-lifecycle-integrity-and-frozen-records
---

# Init scaffolder

`irminsul init` scaffolds a `/docs` skeleton, an `irminsul.toml`, and the two GitHub workflows (PR-time `docs-pr.yml`, nightly `docs-nightly.yml`) into a target codebase. Existing-code adoption auto-detects languages and source roots, then asks for the project name when interactive.

The no-code path distinguishes setup intent:

- **Fresh-start, same repo:** `irminsul init --fresh` creates docs, config, workflows, and an empty `src/` source root. It writes `languages.enabled = []` and does not generate starter code.
- **Fresh-start, private docs / public code:** `irminsul init --fresh --topology docs-only --code-repo owner/code-repo` creates the docs repo now, configures the code checkout as a gitignored subfolder, and allows that code folder to be absent.
- **Docs-only repo for existing separate code:** `irminsul init-docs-only --code-repo owner/repo` keeps the existing two-repo adoption path and detects language/source roots when the code subfolder is already present.

Templates live as Jinja files under `src/irminsul/init/scaffolds/` (`docs/` tree + `irminsul.toml`) and `src/irminsul/init/workflows/` (CI workflows). Output paths mirror the template path with `.j2` stripped.

The scaffold is born compliant with its own configured checks: every layer (including `00-foundation/`, `10-architecture/`, and `80-evolution/rfcs/`) ships a navigation INDEX so sibling docs are never orphans, the tier-3 layer INDEXes carry a Scope & Limitations section, and the INDEX of each not-yet-filled layer is `status: draft`, which the `phantom-layer` check treats as under-construction rather than navigation rot. A freshly initialized repo reports zero errors and zero warnings under the configured check profile.

`detector.detect_languages()` checks for marker files (`pyproject.toml`, `package.json`+`tsconfig.json`, etc.) — cheap heuristics, fast and resilient to weird repo shapes. `detect_source_roots()` filters each detected language's `source_root_candidates` to those that exist on disk, falling back to `["src"]` if nothing matches.

By default, init refuses to overwrite existing files; pass `--force` to replace them. `--fresh` normally errors if code signals already exist, and `--allow-existing-code` makes that intent explicit.

The generated `irminsul.toml` enables `rfc-lifecycle-integrity` in its hard
profile so implemented RFCs are sealed consistently from the first lifecycle.
It also writes discoverable source-policy defaults: empty include/exclude lists
and `honor_gitignore = true`.

## Scope & Limitations

Init scaffolds doc/config/CI structure only — it does not scaffold application code or generate implementation stubs. It does not configure IDEs, editors, or local tooling beyond pre-commit hooks. It does not provision remote services such as GitHub repositories or CI runners.
