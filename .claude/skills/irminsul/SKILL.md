---
name: irminsul
description: Use when editing code or docs in a repo with an irminsul.toml at the root.
---

Run `irminsul orient` first. It reports the docs tree, the configured checks, and
which command to run when.

Follow the work order in `docs/90-meta/agent-protocol.md`.

Before committing, `irminsul check --profile=hard` must exit 0.
