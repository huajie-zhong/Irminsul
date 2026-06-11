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
- [`config`](config.md) — `irminsul.toml` schema
- [`context`](context.md) — task-specific agent navigation context
- [`frontmatter`](frontmatter.md) — per-doc YAML frontmatter parser/validator
- [`docgraph`](docgraph.md) — in-memory representation of a repo's docs
- [`checks`](checks.md) — registered checks; exact names live in `src/irminsul/checks/__init__.py`
- [`languages`](languages.md) — language-profile registry
- [`init`](init.md) — scaffolding command and templates
- [`llm`](llm.md) — LLM client (budget tracking, disk cache, LiteLLM wrapper)
- [`new-list-regen`](new-list-regen.md) — `new`, `list`, `fix`, and `regen agents-md` commands
- [`status`](status.md) — one-glance digest of doc-system health

## Scope & Limitations

This is a navigation index for the 20-components layer. Cross-component interaction and runtime data flows are in [`30-workflows`](../30-workflows/INDEX.md), not here.
