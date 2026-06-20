---
id: 0015-govern-mcp-tool-surface
title: "ADR-0015: Govern the MCP tool surface as a watched surface"
audience: adr
tier: 2
status: stable
describes: []
summary: Govern the MCP tool set with a dedicated `mcp` extractor and a watched `inventory:` block in mcp-server.md (internal consistency), rather than a generic-regex rule or a two-surface CLI-parity check.
---

# ADR-0015: Govern the MCP tool surface as a watched surface

## Status

Accepted, 2026-06-20. Resolves [`0028-mcp-tool-surface-governance`](../80-evolution/rfcs/0028-mcp-tool-surface-governance.md).

## Context

The MCP server (`src/irminsul/mcp_server.py`) exposes the doc graph as a set of
`@server.tool()` registrations, mirrored in [`mcp-server`](../20-components/mcp-server.md)'s
"Exposed tools" list. PR #32 grew that set 7 → 9 (`orient`, `anchors`). It is a
hand-maintained enumeration of the CLI's read commands, and nothing kept it honest —
the exact dogfood-anti-drift case RFC-0027 solved for `orient`'s command vocabulary.
With the watched-surface mechanism already on `main` (`inventory-drift` plus the
`InventoryEntry` `complete`/`omit`/`fingerprints` fields), governing the tool set was a
question of *how to derive the surface* and *what to enforce*.

## Decision

Add a dedicated `mcp` extractor (`src/irminsul/inventory/mcp.py`, registered in
`EXTRACTOR_REGISTRY`) that AST-walks `@server.tool()`-decorated functions and returns
their names as identities. Govern the tool set for **internal consistency** via a watched
`inventory:` block (`kind: mcp`, `complete: true`) in [`mcp-server`](../20-components/mcp-server.md): `inventory-drift`
flags any registered tool not declared, and any declared item not registered. No
`fingerprints` are pinned by default (completeness is enough; the extractor sets each
item's `symbol` so freshness can be opted into later). The `mcp` kind is excluded from the
`liar` prose heuristic, because MCP tool identities are Python function names that shadow
CLI command names docs legitimately backtick-quote.

## Alternatives Considered

- **A `generic_regex` rule instead of a built-in extractor.** Rejected: the generic
  extractor is line-oriented and cannot tie a `@server.tool()` decorator to the `def` on
  the following line, so it cannot reliably name the tools. A dedicated extractor is also
  symmetric with `cli`/`http`/`exports`/`env-vars` and makes the surface queryable via
  `irminsul surface mcp`.
- **CLI parity (every CLI read command must have an MCP tool, or an explicit `omit`).**
  The stronger guarantee, but it requires relating two surfaces (MCP tools ↔ CLI commands)
  — new check machinery beyond the single-surface watched-surface primitive. Deferred;
  internal consistency plus the existing `cli` watched surface on [`orient`](../20-components/orient.md) already
  covers most drift.
- **A hand-rolled test importing the server and asserting the tool set.** Rejected: the
  precise anti-pattern RFC-0027 set out to eliminate — governs only this project and
  reaches into internals.

## Consequences

- A tool added, removed, or renamed in `mcp_server.py` is flagged by `inventory-drift`
  until the [`mcp-server`](../20-components/mcp-server.md) doc's `items` are updated (or the tool is added to `omit`).
- `irminsul surface mcp` now derives the live tool list on demand, like the other surfaces.
- The MCP tool set is no longer governed against the CLI read-command surface; a read
  command added to the CLI without a matching tool is not flagged here. That parity gap is
  left to a future ADR if it proves needed.
- `liar` carries a one-kind exclusion (`mcp`); future non-prose surface kinds would join it.
