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
  - tests/test_init_siblings.py
implements:
  - 0035-rfc-lifecycle-integrity-and-frozen-records
---

# Init scaffolder

`irminsul init` scaffolds a `/docs` skeleton, an `irminsul.toml`, and the two GitHub workflows (PR-time `docs-pr.yml`, nightly `docs-nightly.yml`) into a target codebase. Existing-code adoption auto-detects languages and source roots when possible; explicit `--language` values take precedence.

`--topology` selects one of the two supported repository layouts ([`ADR-0022`](../50-decisions/0022-reduce-supported-repository-topologies.md)), and there are three paths through the command:

- **Adopt existing same-repo code:** `irminsul init` detects languages and source roots in place.
- **Fresh-start, same repo:** `irminsul init --fresh --language python` creates docs, config, workflows, and an empty `src/` source root without generating starter code. Interactive runs prompt for at least one language when the option is omitted; non-interactive runs require it.
- **Docs repo beside a separate code repo:** `irminsul init --topology siblings --code-repo owner/code-repo --language python` writes `source_roots` reaching through `../` and generates two-checkout CI. When the code repo already exists locally, init detects its languages and source roots unless explicit languages were supplied. When the repo is unavailable or detection finds no supported language, interactive runs prompt and non-interactive runs require `--language`. `--code-repo` values that do not resolve to a direct sibling of the docs repo are rejected. See [private docs](../30-workflows/private-docs.md) for the layout.

`--language` accepts `python`, `typescript`, `go`, or `rust` and may be repeated. Generated config uses registry order and removes duplicates, so the same selected profiles always produce the same `languages.enabled` list.

Templates live as Jinja files under `src/irminsul/init/scaffolds/` (`docs/` tree + `irminsul.toml`) and `src/irminsul/init/workflows/<topology>/` (CI workflows). Output paths mirror the template path with `.j2` stripped, and workflow templates flatten into `.github/workflows/`. The two topologies get separate workflow templates rather than one branching template: the sibling gate needs two checkouts under a common parent plus a `working-directory`, which the composite Action cannot express, so it installs and calls the CLI directly.

The scaffold is born compliant with its own configured checks: every layer (including `00-foundation/`, `10-architecture/`, and `80-evolution/rfcs/`) ships a navigation INDEX so sibling docs are never orphans, the tier-3 layer INDEXes carry a Scope & Limitations section, and the INDEX of each not-yet-filled layer is `status: draft`, which the `phantom-layer` check treats as under-construction rather than navigation rot. A freshly initialized repo reports zero errors and zero warnings under the configured check profile.

`detector.detect_languages()` checks for marker files (`pyproject.toml`, `package.json`+`tsconfig.json`, etc.) — cheap heuristics, fast and resilient to weird repo shapes. `detect_source_roots()` filters each detected language's `source_root_candidates` to those that exist on disk, falling back to `["src"]` if nothing matches.

By default, init refuses to overwrite existing files; pass `--force` to replace them. `--fresh` normally errors if code signals already exist, and `--allow-existing-code` makes that intent explicit.

The generated `irminsul.toml` enables `rfc-lifecycle-integrity` in its hard
profile so implemented RFCs are sealed consistently from the first lifecycle.
It also writes discoverable source-policy defaults: empty include/exclude lists
and `honor_gitignore = true`.

## Scope & Limitations

Init scaffolds doc/config/CI structure only — it does not scaffold application code or generate implementation stubs. It does not configure IDEs, editors, or local tooling beyond pre-commit hooks. It does not provision remote services such as GitHub repositories or CI runners.
