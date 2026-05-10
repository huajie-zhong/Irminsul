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
- [`frontmatter`](frontmatter.md) — per-doc YAML frontmatter parser/validator
- [`docgraph`](docgraph.md) — in-memory representation of a repo's docs
- [`checks`](checks.md) — registered checks; exact names are generated in the [check registries reference](../40-reference/check-registries.md)
- [`languages`](languages.md) — language-profile registry
- [`render`](render.md) — MkDocs renderer
- [`init`](init.md) — scaffolding command and templates
- [`llm`](llm.md) — LLM client (budget tracking, disk cache, LiteLLM wrapper)
- [`new-list-regen`](new-list-regen.md) — `new`, `list`, `fix`, and `regen` commands
