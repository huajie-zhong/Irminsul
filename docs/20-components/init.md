---
id: init
title: Init scaffolder
audience: explanation
tier: 3
status: stable
describes:
  - src/irminsul/init/**
tests:
  - tests/test_init.py
  - tests/test_init_detector.py
  - tests/test_init_docs_only.py
---

# Init scaffolder

`irminsul init` scaffolds a `/docs` skeleton, an `irminsul.toml`, and the two GitHub workflows (PR-time `docs-pr.yml`, nightly `docs-nightly.yml`) into a target codebase. Existing-code adoption auto-detects languages and source roots, then asks for project name and render target when interactive.

The no-code path distinguishes setup intent:

- **Fresh-start, same repo:** `irminsul init --fresh` creates docs, config, workflows, and an empty `src/` source root. It writes `languages.enabled = []` and does not generate starter code.
- **Fresh-start, private docs / public code:** `irminsul init --fresh --topology docs-only --code-repo owner/future-repo` creates the docs repo now, configures the future code checkout as a gitignored subfolder, and allows that code folder to be absent.
- **Docs-only repo for existing separate code:** `irminsul init-docs-only --code-repo owner/repo` keeps the existing two-repo adoption path and detects language/source roots when the code subfolder is already present.

Templates live as Jinja files under `src/irminsul/init/scaffolds/` (`docs/` tree + `irminsul.toml`) and `src/irminsul/init/workflows/` (CI workflows). Output paths mirror the template path with `.j2` stripped.

`detector.detect_languages()` checks for marker files (`pyproject.toml`, `package.json`+`tsconfig.json`, etc.) — cheap heuristics, fast and resilient to weird repo shapes. `detect_source_roots()` filters each detected language's `source_root_candidates` to those that exist on disk, falling back to `["src"]` if nothing matches.

By default, init refuses to overwrite existing files; pass `--force` to replace them. `--fresh` normally errors if code signals already exist, and `--allow-existing-code` makes that intent explicit.
