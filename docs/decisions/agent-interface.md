---
id: agent-interface
title: Agent interface
status: stable
describes: []
summary: Agents orient, gather context, and query references through read-only commands and an MCP server, guided by a generated manifest, a written work order, and harness wiring scaffolded at adoption.
retires:
  - id: context-change-alias
    kind: concept
    matches:
      - context --change
    guidance: Run `irminsul change status <id>` for an RFC's evidence report.
---

# Agent interface

## Status

Accepted, 2026-09-12. The "Context is stateless" bullet is qualified by
[Context keeps no session; external checks may cache observations](context-keeps-no-session-external-checks-may-cache-observations.md),
which separates context's own statelessness from an external check's cache.

## Context

Coding agents do most of the editing in repositories that adopt Irminsul. They need to
find what owns a file, what depends on it, and what they must update, without reading
the whole tree, and they need that through the harness they already run.

## Decision

- **Read commands with JSON.** `orient`, `context`, `refs`, `surface`, `check`, `list`,
  and `anchors` all support `--format json`. `orient` is the first call and teaches the
  rest of the vocabulary, kept honest against the live CLI by a watched inventory.
- **Context is stateless.** `context --before-edit <path...>` packages owners, tests,
  dependencies, active RFCs, findings, and bounded excerpts; `context --after-edit`
  inspects the working tree and runs hard validation. Nothing persists between calls.
- **A read-only MCP server** exposes the same queries and the read side of the change
  lifecycle. Writes stay confirmed CLI actions until MCP has an authorization model.
- **A generated manifest and a written protocol.** The [agent manifest](../AGENTS.md) carries a generated
  navigation table plus curated sections, and the agent protocol records the work order.
  The root [`AGENTS.md`](../../AGENTS.md) is the single harness-neutral entry point.
- **Harness wiring is scaffolded, not policed.** Adoption writes an MCP registration, a
  trigger-only skill, and a Claude Code pointer as constants, skips existing files, and
  merges the registration and pointer under `--force`. No check watches them.

## Alternatives Considered

- **A persistent agent session or index.** Rejected: re-deriving on every call cannot go
  stale.
- **MCP write tools now.** Rejected until writes have an authorization model.
- **A drift check on the harness files.** Rejected: none is derived from anything, so the
  check would compare a constant with itself and burden adopters who delete a file.

## Consequences

- An agent can work the edit loop from `orient` and two context calls.
- Wiring that a later release changes does not reach repositories that already adopted.
