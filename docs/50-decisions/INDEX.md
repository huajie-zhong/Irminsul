---
id: 50-decisions
title: Architecture decisions
audience: reference
tier: 2
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Architecture decisions (ADRs)

ADRs are the canonical home for *why*. Use the standard template (Michael Nygard's original works fine):

```
# ADR 0042: Adopt event sourcing for the order service

## Status
Accepted, 2026-04-01. Supersedes ADR-0019.

## Context
What forces are at play? What are we currently doing?

## Decision
What we will do.

## Alternatives Considered
What we explicitly rejected, and why.

## Consequences
What becomes easier. What becomes harder. What new risks appear.
```

Two non-obvious rules:
- **ADRs are append-only.** Never edit a past ADR's decision. If it changes, write a new one and mark the old as `Superseded by ADR-XXXX`.
- **The "Alternatives Considered" section is mandatory.** Without it, future contributors will keep proposing the same rejected ideas.
