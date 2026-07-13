---
id: 20-components
title: Components
audience: reference
tier: 3
status: stable
describes: []
tests:
  - tests/
---

# Components

Each architectural piece of Irminsul has a dedicated doc here. Frontmatter `describes:` claims map components to source paths.

- [`cli`](cli.md) — CLI entry point
- [`change`](change.md) — bound-change lifecycle reports and transitions for RFCs
- [`config`](config.md) — `irminsul.toml` schema
- [`orient`](orient.md) — first-call agent orientation report
- [`context`](context.md) — task-specific agent navigation context
- [`frontmatter`](frontmatter.md) — per-doc YAML frontmatter parser/validator
- [`docgraph`](docgraph.md) — in-memory representation of a repo's docs
- [`baseline`](baseline.md) — brownfield ratchet: grandfather existing findings, fail only on new ones
- [`checks`](checks.md) — registered checks; exact names live in `src/irminsul/checks/__init__.py`
- [`languages`](languages.md) — language-profile registry
- [`init`](init.md) — scaffolding command and templates
- [`new-list-regen`](new-list-regen.md) — `new`, `list`, `fix`, and `regen agents-md` commands
- [`mcp-server`](mcp-server.md) — read-only MCP stdio server for AI agents
- [`status`](status.md) — one-glance digest of doc-system health

## Scope & Limitations

This is a navigation index for the 20-components layer. Cross-component interaction and runtime data flows are in [`30-workflows`](../30-workflows/INDEX.md), not here.
