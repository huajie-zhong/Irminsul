---
id: ship-framework-packs-with-kind-capabilities
title: Ship framework packs with kind capabilities
status: stable
describes: []
summary: Code surfaces for popular stacks ship as built-in data packs, and checks read a kind's declared capabilities instead of branching on its name.
---

# Ship framework packs with kind capabilities

## Status

Accepted, 2026-09-13.

## Context

Code surfaces understood only Python frameworks, and general checks named specific
kinds, so supporting another language meant editing checks. Asking every adopter to
write regular-expression rules instead would put the work on the people least placed
to do it.

## Decision

Ship built-in framework packs for Typer, Click, argparse, FastAPI, Flask, cobra, clap,
commander, Express, and a Python MCP server. A pack is data: rules made of a kind, a
file glob, a pattern, and an identity template, alongside the existing AST extractors.
Every pack is active unless `frameworks.enabled` narrows the set.

Each kind resolves to capabilities — a mention pattern and whether prose names it in
context — which `inventory-drift`, `liar`, and `list review` read instead of kind names.
Configuration rules accept the same identity template and capabilities. The review
queue derives program names from package manifests, overridable with
`frameworks.command_names`.

## Alternatives Considered

- **Configuration rules only.** Rejected: every non-Python adopter would write regex.
- **Detect frameworks at `init` and enable only those.** Rejected as the default: a
  framework added later would silently yield nothing.
- **A custom parser per framework.** Rejected for now: data packs follow the language
  profile precedent, and a pack can gain an AST extractor later.

## Consequences

- A cobra, clap, commander, or Express project gets commands, options, and routes with
  no configuration.
- Regex packs miss names an AST would infer, such as a Click command named only by its
  function.
