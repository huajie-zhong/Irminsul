---
id: tooling
title: Tooling Stack and Deployment
audience: explanation
tier: 2
status: stable
describes: []
---

# Tooling Stack and Deployment

## Suggested Tooling Stack

Concrete recommendations for external tools. None of these are load-bearing — substitute equivalents freely.

- **Optional renderer:** GitHub and IDE Markdown previews require no setup. For a published site, point MkDocs, Docusaurus, or another renderer at the portable docs tree; Irminsul does not ship or configure one.
- **Diagrams:** Mermaid for everything that fits its grammar (sequence, flowchart, ER, state). PlantUML or Excalidraw for the rest. Always source-controlled, never image-only.
- **API reference:** OpenAPI generated from code, rendered with Redoc or Swagger UI.
- **Code-derived reference:** Prefer `irminsul surface` for supported CLI, HTTP, export, environment-variable, and MCP surfaces. Use language-specific generators for other surfaces without committing the result as canonical prose.
- **ADR management:** `adr-tools` CLI or `log4brains`.
- **Linting:** `markdownlint` for syntax, `Vale` for prose style.
- **Link checking:** `lychee` (fast Rust-based) for both internal and external.
- **Pre-commit:** the `pre-commit` framework, with hooks pinned by hash.
- **CI:** GitHub Actions, with `Danger.js` for PR-time policy enforcement.
- **Spell/grammar:** `cspell` with a project dictionary that the glossary feeds.

## Packaging the System for Reuse

The doc system itself — validators, drift detectors, ADR templates, frontmatter schema, and scaffolded CI workflows — is codebase-agnostic. It lives in Irminsul and is consumed by codebases as a dependency rather than copied into each one. Docs are normally co-located with code; the supported private-docs topologies preserve filesystem access when repository ownership requires separation.

### The Distinction That Matters

| Lives in dedicated tooling repo | Lives in each codebase |
|---|---|
| Frontmatter schema definition | Actual frontmatter in each doc |
| Glob / source ownership coverage / uniqueness checkers | Doc files claiming source paths |
| On-demand surface extractors | The `/docs` folder content |
| Diátaxis layer skeleton | Codebase-specific glossary |
| ADR / RFC templates | Actual ADRs and RFCs |
| GitHub Actions workflow definitions | `irminsul.toml` config |
| Pre-commit hook definitions | Repo-specific overrides |

### Why Co-Location Is the Default

The Change Triplet (code + tests + docs in one PR) is simplest in one repository: review is atomic, history is shared, and source-ownership checks have direct filesystem access. Separate private docs are still supported when the code checkout is available through a configured source root. That topology cannot make two repositories atomic, so its coordination limits remain explicit.

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

### Topology of the Two-Repo Setup

The canonical setup, limitations, path semantics, and CI examples for nested and sibling code checkouts live in [Private docs for a public code repo](../30-workflows/private-docs.md). Keeping that operational detail in one place prevents the supported topology from drifting between architecture and workflow docs.

### Adopting on a New Codebase

For an existing same-repo codebase, adoption is roughly:

1. Add the tool as a dev dependency.
2. Run `irminsul init` — generates `/docs` skeleton, `irminsul.toml`, GitHub Actions workflow, and pre-commit hooks.
3. Write [`00-foundation/principles.md`](../00-foundation/principles.md) and [`10-architecture/overview.md`](overview.md).
4. Commit. CI can run the system from PR #1.

For a fresh same-repo project with no code yet:

1. Run `irminsul init --fresh --path my-new-project`.
2. Add application code under `src/` when the project generator or first implementation is ready.
3. Write the foundation and architecture docs.
4. Commit. CI can run the system from PR #1.

For an existing public-code + private-docs case:

1. Create an empty docs-only private repo.
2. Run `irminsul init-docs-only --code-repo owner/public-repo` inside it.
3. Clone the public repo locally: `git clone https://github.com/owner/public-repo`.
4. Write the foundation and architecture docs.
5. Commit. CI checks out both repos on every PR.

For fresh public-code + private-docs setup, use `irminsul init --fresh --topology docs-only --code-repo owner/future-public-repo`. The code repo checkout folder is gitignored and may be absent until the public repo exists.
