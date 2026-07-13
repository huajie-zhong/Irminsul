---
id: 30-workflows
title: Workflows
audience: explanation
tier: 3
status: draft
describes: []
tests:
  - tests/
---

# Workflows

Cross-component narratives — how a request flows through the system, how a user account is created, how data ingest happens end to end.

- [`check-pipeline`](check-pipeline.md) — how a check run flows from CLI invocation to exit code
- [`private-docs`](private-docs.md) — keeping the docs tree private beside an open-source code repo

## Scope & Limitations

Only the check pipeline and private-docs flows are currently documented. Init and regen flows are not yet written. This layer does not cover configuration authoring or CI integration — those are in [`00-foundation`](../00-foundation/enforcement.md) and [`60-operations`](../60-operations/INDEX.md).
