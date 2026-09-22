---
id: overview
title: Architecture overview
status: stable
describes: []
claims:
  - id: checks-consume-the-graph
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: A check receives the DocGraph built once for the invocation and returns a list of Findings; that signature is the whole interface between the pipeline and a check.
    evidence:
      - src/irminsul/docgraph.py
      - src/irminsul/checks/pipeline.py
  - id: action-adds-no-logic
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: The composite Action installs the CLI and calls it; behaviour belongs in the CLI so that a local run and a CI run cannot diverge.
    evidence:
      - action.yml
      - src/irminsul/cli.py
---

# Architecture overview

Irminsul is a Python CLI invoked from CI. It reads a target codebase's `/docs` tree and `irminsul.toml`, builds an in-memory `DocGraph`, runs a registered set of checks, and exits 0 or non-zero based on whether any error-severity findings were produced. There are no servers and no hosted services; the only state kept between runs is on-disk files in the repository, such as a baseline and the external-link cache.

```mermaid
flowchart LR
    user[User / CI] -->|invokes| cli[irminsul CLI]
    cli -->|loads| toml[irminsul.toml]
    cli -->|walks| docs[/docs/]
    cli -->|reads| src[/source roots/]
    cli -->|builds| graph[DocGraph]
    graph --> checks[Enabled checks]
    checks -->|findings| cli
    cli -->|exit 0/1| user
```
## Structure

The Irminsul documentation system dictates strict structural rules for a codebase's documentation:
- **[The Layered Directory Structure](layers.md)** defines where docs are placed and which rules each layer's docs follow.

## Components

- The **CLI** ([`cli.md`](../components/cli.md)) is the user-facing entry point. The exact command surface is derived on demand via `irminsul surface cli`.
- The **config** ([`config.md`](../components/config.md)) is a Pydantic schema for `irminsul.toml`.
- The **frontmatter parser** ([`frontmatter.md`](../components/frontmatter.md)) validates per-doc YAML frontmatter against the `DocFrontmatter` schema.
- The **DocGraph** ([`docgraph.md`](../components/docgraph.md)) is the canonical in-memory representation of a repo's docs.
- The **checks** ([`checks.md`](../components/checks.md)) consume a DocGraph and emit findings. The exact check surface is the registry in `src/irminsul/checks/__init__.py`.
- The **language profiles** ([`languages.md`](../components/languages.md)) are pure-data records (source-root candidates + schema-leak regexes) keyed by language name.
- The **init scaffolder** ([`init.md`](../components/init.md)) walks Jinja templates to bootstrap a new codebase's `/docs` tree, `irminsul.toml`, and CI workflows.

Cross-cutting: the [composite GitHub Action](../components/init.md) (`action.yml` at repo root) wraps the CLI for one-line CI integration. The Dockerfile produces a `ghcr.io` image used in CI systems that prefer container steps.

## What's not here

- No backend service. No webhooks. Nothing persists between invocations except repository files such as the baseline and the external-link cache.
- No LLM calls anywhere. Every check is deterministic; semantic judgment belongs to the coding agent consuming Irminsul, not to the tool itself.
- No network access unless `checks.external_links.enabled` turns on the external-link check, whose findings are time findings.
