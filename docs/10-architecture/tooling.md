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
| Glob / source ownership coverage / uniqueness checkers | Doc files claiming source paths |
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

### Topology of the Two-Repo Setup

The "code public + docs private" row in the decision table above requires clarification because "code is in a separate repo" is ambiguous:

| Sense of "elsewhere" | Supported in v0.2.0 |
|---|---|
| **Elsewhere in git ownership** — code lives in a different GitHub/GitLab repo (public, private, or a different org) | ✅ Yes — `irminsul init-docs-only` |
| **Elsewhere on the filesystem** — code lives at a sibling path like `../my-public-code/` without being inside the docs repo | ❌ No — deferred to Sprint 3 (Topology B) |

#### Topology A (v0.2.0) — code nested inside docs repo

The code repo is cloned as a **gitignored subfolder** inside the docs repo. CI checks it out as a secondary `actions/checkout@v4` step.

```
docs-private-repo/              ← this repo (private)
├── docs/
├── irminsul.toml               ← source_roots = ["my-public-code/src"]
├── .gitignore                  ← /my-public-code/  ← added by init-docs-only
└── my-public-code/             ← gitignored clone of the public repo
    └── src/
        └── ...
```

Use `irminsul init-docs-only --code-repo acme/my-public-code` to scaffold this topology. The command:
1. Writes the docs skeleton and `irminsul.toml` with `source_roots = ["my-public-code/src"]`.
2. Appends `/my-public-code/` to `.gitignore`.
3. Renders CI workflows with a dual `actions/checkout@v4` step (docs at `.`, code at `my-public-code/`).

#### Topology B (deferred to Sprint 3) — code at a sibling path

The code would live at `../my-public-code/` — outside the docs repo entirely. This is **not supported** in v0.2.0.

**Why:** `walk_source_files` (`src/irminsul/checks/globs.py`) and `_to_repo_relative` (`src/irminsul/docgraph.py`) both call `path.relative_to(repo_root)`, which raises `ValueError` when the path is outside `repo_root`. Lifting that assumption requires a refactor of the path layer and is planned for Sprint 3 as a `--source-root-prefix` option.

### Adopting on a New Codebase

For an existing same-repo codebase, adoption is roughly:

1. Add the tool as a dev dependency.
2. Run `irminsul init` — generates `/docs` skeleton, `irminsul.toml`, GitHub Actions workflow, and pre-commit hooks.
3. Write [`00-foundation/principles.md`](../00-foundation/principles.md) and [`10-architecture/overview.md`](overview.md).
4. Commit. CI now enforces the system from PR #1.

For a fresh same-repo project with no code yet:

1. Run `irminsul init --fresh --path my-new-project`.
2. Add application code under `src/` when the project generator or first implementation is ready.
3. Write the foundation and architecture docs.
4. Commit. CI now enforces the system from PR #1.

For an existing public-code + private-docs case:

1. Create an empty docs-only private repo.
2. Run `irminsul init-docs-only --code-repo owner/public-repo` inside it.
3. Clone the public repo locally: `git clone https://github.com/owner/public-repo`.
4. Write the foundation and architecture docs.
5. Commit. CI checks out both repos on every PR.

For fresh public-code + private-docs setup, use `irminsul init --fresh --topology docs-only --code-repo owner/future-public-repo`. The code repo checkout folder is gitignored and may be absent until the public repo exists.
