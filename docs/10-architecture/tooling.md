---
id: tooling
title: Tooling Stack and Deployment
audience: explanation
tier: 2
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Tooling Stack and Deployment

## Suggested Tooling Stack

Concrete recommendations for external tools. None of these are load-bearing — substitute equivalents freely.

- **Renderer:** MkDocs with the Material theme, or Docusaurus. Both support frontmatter, plugins, and produce static sites.
- **Diagrams:** Mermaid for everything that fits its grammar (sequence, flowchart, ER, state). PlantUML or Excalidraw for the rest. Always source-controlled, never image-only.
- **API reference:** OpenAPI generated from code, rendered with Redoc or Swagger UI.
- **Schema reference:** `mkdocstrings` (Python), `typedoc` (TS), `protoc-gen-doc` (Protobuf), or hand-rolled scripts.
- **ADR management:** `adr-tools` CLI or `log4brains`.
- **Linting:** `markdownlint` for syntax, `Vale` for prose style.
- **Link checking:** `lychee` (fast Rust-based) for both internal and external.
- **Pre-commit:** the `pre-commit` framework, with hooks pinned by hash.
- **CI:** GitHub Actions, with `Danger.js` for PR-time policy enforcement.
- **Spell/grammar:** `cspell` with a project dictionary that the glossary feeds.
- **LLM judge:** any cheap model with structured output. Treat as advisory, never blocking.

## Packaging the System for Reuse

The doc system itself — validators, drift detectors, renderer config, ADR templates, frontmatter schema, CI workflows — is codebase-agnostic. It lives in its own repository (Irminsul) and is consumed by codebases as a dependency, never copy-pasted into each one. The actual *docs* must live with the code; the *tooling* should not.

### The Distinction That Matters

| Lives in dedicated tooling repo | Lives in each codebase |
|---|---|
| Frontmatter schema definition | Actual frontmatter in each doc |
| Glob / coverage / uniqueness checkers | Doc files claiming source paths |
| Renderer config (MkDocs, Docusaurus) | The `/docs` folder content |
| Diátaxis layer skeleton | Codebase-specific glossary |
| ADR / RFC templates | Actual ADRs and RFCs |
| GitHub Actions workflow definitions | `irminsul.toml` config |
| Pre-commit hook definitions | Repo-specific overrides |
| LLM judge prompts | The codebase's source code |

### Why Co-Location of Docs Is Non-Negotiable

The Change Triplet (code + tests + docs in one PR) requires single-repo atomicity. If docs live in a separate repo, every code change becomes two PRs across two repos with manual coordination — they will desynchronize within weeks. Drift detection by mtime requires single git history. Coverage checks (every source file claimed by some doc) require trivial filesystem access to source. None of this works across repo boundaries without painful sync infrastructure that breaks more often than it works.

### Why Centralization of Tooling Is the Multiplier

The tooling has zero dependency on any specific codebase. Centralizing it gives you one place to fix a bug, one place to add a check, one place to roll out a new convention to every codebase that uses the system. New checks reach all consumers via dependency upgrade.

### Shape of the Package

Each consuming codebase has a single config file at root (`irminsul.toml`) declaring its specifics. The tool reads this config, runs the configured checks, and exits with appropriate status codes for CI. Codebases get standardization for free; the tooling repo gets one canonical home for improvements.

### Visibility: All-Private Is the Default

Most projects keep all docs private. **If your code is also private** (the typical company codebase), this is trivial — single repo, every check works as designed, no special handling.

The only non-trivial case is **code public + docs private**: docs live in their own private repo; code in a public repo; the doc-system tool runs only against the private docs repo. The Change Triplet works inside the private docs repo for internal contributors; external contributors submit code-only PRs and an internal reviewer updates docs as part of merge.

Decision Table:

| Code | Docs | Setup | When to pick |
|------|------|-------|--------------|
| Private | Private | Single repo | Company codebase. Default. |
| Public | Private | Two repos, all-private docs | Public code where API stability > community participation |
| Public | Public | Single repo | Pure community OSS |

### Adopting on a New Codebase

Once the tooling repo exists, adopting it on a new codebase is roughly:

1. Add the tool as a dev dependency.
2. Run `irminsul init` — generates `/docs` skeleton, `irminsul.toml`, GitHub Actions workflow, and pre-commit hooks.
3. Write `00-foundation/principles.md` and `10-architecture/overview.md`.
4. Commit. CI now enforces the system from PR #1.
