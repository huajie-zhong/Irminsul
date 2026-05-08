---
id: 20-components
title: Components
audience: reference
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Components

Each architectural piece of Irminsul has a dedicated doc here. Frontmatter `describes:` claims map components to source paths.

- [`cli`](cli.md) — CLI entry point
- [`config`](config.md) — `irminsul.toml` schema
- [`frontmatter`](frontmatter.md) — per-doc YAML frontmatter parser/validator
- [`docgraph`](docgraph.md) — in-memory representation of a repo's docs
- [`checks`](checks.md) — the five hard checks
- [`languages`](languages.md) — language-profile registry
- [`render`](render.md) — MkDocs renderer
- [`init`](init.md) — scaffolding command and templates
