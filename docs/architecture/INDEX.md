---
id: architecture
title: Architecture
status: stable
describes: []
---

# Architecture

The shape of the system: which layers exist, how parts compose, what tools render or check it.

- [`overview`](overview.md) — high-level picture of CLI → DocGraph → Checks → CI
- [`check-pipeline`](check-pipeline.md) — how `irminsul check` flows from invocation to exit code
- [`component-hierarchy`](component-hierarchy.md) — how components nest
- [`levels-and-views`](levels-and-views.md) — C4 zoom levels and cross-cutting views for architecture docs
- [`layers`](layers.md) — the six layers and the rules each sets
- [`tooling`](tooling.md) — external tools that complement Irminsul, and the repository layouts it supports
