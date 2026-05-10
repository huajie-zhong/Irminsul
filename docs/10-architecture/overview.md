---
id: overview
title: Architecture overview
audience: explanation
tier: 2
status: stable
describes: []
---

# Architecture overview

Irminsul is a Python CLI invoked from CI. It reads a target codebase's `/docs` tree and `irminsul.toml`, builds an in-memory `DocGraph`, runs a registered set of checks, and exits 0 or non-zero based on whether any error-severity findings were produced. There are no servers, no hosted services, no persistent state.

```mermaid
flowchart LR
    user[User / CI] -->|invokes| cli[irminsul CLI]
    cli -->|loads| toml[irminsul.toml]
    cli -->|walks| docs[/docs/]
    cli -->|reads| src[/source roots/]
    cli -->|builds| graph[DocGraph]
    graph --> checks[Hard checks]
    checks -->|findings| cli
    cli -->|exit 0/1| user
    cli -->|render| mkdocs[MkDocs Material site]
```
## Structure

The Irminsul documentation system dictates strict structural rules for a codebase's documentation:
- **[The Tier System](tiers.md)** defines maintenance and enforcement rules based on the doc's tier (T1-T4).
- **[The Layered Directory Structure](layers.md)** enforces exactly where docs should be placed based on their specificity.

## Components

- The **CLI** ([`cli.md`](../20-components/cli.md)) is the user-facing entry point. The exact command surface is generated in the [CLI commands reference](../40-reference/cli-commands.md).
- The **config** ([`config.md`](../20-components/config.md)) is a Pydantic schema for `irminsul.toml`.
- The **frontmatter parser** ([`frontmatter.md`](../20-components/frontmatter.md)) validates per-doc YAML frontmatter against Appendix B of the reference.
- The **DocGraph** ([`docgraph.md`](../20-components/docgraph.md)) is the canonical in-memory representation of a repo's docs.
- The **checks** ([`checks.md`](../20-components/checks.md)) consume a DocGraph and emit findings. The exact check surface is generated in the [check registries reference](../40-reference/check-registries.md).
- The **language profiles** ([`languages.md`](../20-components/languages.md)) are pure-data records (source-root candidates + schema-leak regexes) keyed by language name.
- The **renderer** ([`render.md`](../20-components/render.md)) is a small Protocol with one MkDocs Material implementation.
- The **init scaffolder** ([`init.md`](../20-components/init.md)) walks Jinja templates to bootstrap a new codebase's `/docs` tree, `irminsul.toml`, and CI workflows.

Cross-cutting: the [composite GitHub Action](../20-components/init.md) (`action.yml` at repo root) wraps the CLI for one-line CI integration. The Dockerfile produces a `ghcr.io` image used in CI systems that prefer container steps.

## What's not here

- No backend service. No webhooks. No state persisted between invocations.
- No LLM calls in the v0.1.0 hard-check path. The `litellm` dependency is wired but unused; LLM advisory checks land in Sprint 2.
- No git history queries in the hard-check path. `mtime` drift, supersession auto-update, and the stale reaper land in Sprint 2.
