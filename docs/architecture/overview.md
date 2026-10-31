---
id: overview
title: Architecture overview
status: stable
summary: High-level picture of CLI → DocGraph → Checks → CI.
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
    pinned:
      src/irminsul/docgraph.py: sha256:9190f540e920
      src/irminsul/checks/pipeline.py: sha256:b54acfc1df14
  - id: action-adds-no-logic
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: The composite Action installs the CLI and calls it; behaviour belongs in the CLI so that a local run and a CI run cannot diverge.
    evidence:
      - action.yml
      - src/irminsul/cli.py
    pinned:
      action.yml: sha256:565555652eab
      src/irminsul/cli.py: sha256:4c0c238eafa7
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

Every check receives the `DocGraph` built once for the run and returns a list of findings; that signature is the whole interface between the pipeline and a check. <!-- claim:checks-consume-the-graph -->

The composite Action (`action.yml`) installs the CLI and calls it, holding no logic of its own, so a local run and a CI run cannot diverge. <!-- claim:action-adds-no-logic -->

## Structure

[Layers](layers.md) defines where docs are placed and which rules each layer's docs follow; the generated [manifest](../AGENTS.md) lists every doc with its summary.

## What's not here

- No backend service. No webhooks.
- No GitHub App. An App is slicker but requires hosted infrastructure; the CLI runs anywhere CI runs, the composite Action wraps it for GitHub, and a project can call the CLI from its own pre-commit hook.
- No LLM calls anywhere. Every check is deterministic; semantic judgment belongs to the coding agent consuming Irminsul, not to the tool itself.
- No network access unless `checks.external_links.enabled` turns on the external-link check, whose findings are time findings.
