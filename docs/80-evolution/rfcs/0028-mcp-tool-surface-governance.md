---
id: 0028-mcp-tool-surface-governance
title: "Govern the MCP tool surface as a watched surface"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0028: Govern the MCP tool surface as a watched surface

## Summary

The MCP server exposes the doc graph as a fixed set of tools — the `@server.tool()`
registrations in [`mcp-server`](../../20-components/mcp-server.md)
(`src/irminsul/mcp_server.py`), mirrored in that doc's "Exposed tools" list and its
`depends_on`. That set is a **hand-maintained enumeration of the CLI's read
commands**, and PR #32 grows it (adds `orient` and `anchors`, 7 → 9 tools).
Nothing keeps it honest: there is no check that the tool list matches the CLI read
surface, nor that the doc's bullets match the registered tools. This RFC proposes
governing the MCP tool set with the [watched-surface](0027-watched-surfaces.md)
mechanism so that a new, removed, or renamed tool is flagged for review the same
way `orient`'s command vocabulary already is.

This is a proposal only. PR #32 ships the (currently ungoverned) `orient`/`anchors`
MCP tools; implementing this governance is deliberately deferred.

## Motivation

The project's dogfood-anti-drift stance is that **new hand-maintained enumerations
should be governed by irminsul's own primitives**, not by trust or a bespoke test.
RFC 0027 applied exactly this to `orient`: its curated command vocabulary is now a
watched surface, kept honest against the live CLI by `inventory-drift` via
`orient.md`'s `inventory:` block.

The MCP tool set is the *same class* of artifact — a curated mirror of the CLI read
commands — but it is governed in **zero** directions today:

- **Drift from the CLI.** A read command renamed, removed, or added in `cli.py` does
  not flag the MCP tool list. The tool set can silently fall behind the surface it
  claims to mirror.
- **Doc/code skew.** The "Exposed tools" bullets and `depends_on` in `mcp-server.md`
  are maintained by hand against the `@server.tool()` registrations; nothing checks
  that the prose list equals the registered set.

PR #32 makes this concrete: it is the change that introduces the un-governed growth,
which is the right moment to record the follow-up — mirroring how RFC 0027 recorded
its own implementing PRs (#45 → #47).

## Detailed Design (sketch)

The goal is to make the MCP tool set a **derivable surface** so that an
`inventory:` block in `mcp-server.md` (with `complete: true`) lets `inventory-drift`
flag new / removed / renamed tools, exactly as for `orient`.

The open piece is *how to derive the surface*. Two candidates:

- **(a) A dedicated `mcp` extractor.** A new extractor under `src/irminsul/inventory/`
  that parses the `@server.tool()`-decorated functions out of `mcp_server.py` and
  returns their names as identities. Symmetric with the existing `cli`/`http`/
  `exports`/`env-vars` extractors; registered in `EXTRACTOR_REGISTRY`. Adding a
  language/surface is "add a file here," per the inventory design.
- **(b) A `generic_regex` rule.** Declare a config-level generic kind that matches
  the `@server.tool()` registration shape. Lighter (no new built-in), but more
  brittle and less self-describing than a real extractor.

A second design axis — independent of (a)/(b) — is **what to govern**:

- **Internal consistency** — the doc's declared tool list matches the tools actually
  registered in `mcp_server.py`. Catches doc/code skew.
- **CLI parity** — every CLI read command has a corresponding MCP tool (or an
  explicit `omit:`, e.g. the deliberately MCP-excluded write commands `fix`, `new`,
  `regen`, `seed`, and `anchors --re-pin`). Catches drift from the mirrored surface.

CLI parity is the stronger guarantee and the closer analogue to what RFC 0027 does
for `orient`; it likely requires relating two surfaces (MCP tools ↔ CLI commands)
rather than watching one in isolation.

## Alternatives

- **Status quo / a hand-rolled test** importing the server and asserting the tool
  set — the exact anti-pattern RFC 0027 set out to eliminate for `orient`. Works
  locally, governs only this project, reaches into internals.
- **Generic-regex rule instead of a built-in extractor** — see (b); viable as an
  interim, weaker as a long-term mirror of a first-party surface.
- **Do nothing** — accept that the MCP tool list is small and hand-reviewed. Cheap
  today, but it is precisely the kind of enumeration that drifts as the CLI grows.

## Unresolved Questions

- **(a) vs (b)** — dedicated `mcp` extractor, or a generic-regex rule?
- **Internal consistency vs. CLI parity** — govern one surface, or relate the MCP
  tool set to the CLI read-command surface?
- **Freshness** — do RFC 0027 `fingerprints` apply to tools (flag when a tool's
  underlying query changes), or is completeness (new/removed/renamed) enough?
- **Sequencing** — does this depend on RFC 0027 Phase 2 (freshness) landing first,
  or can the completeness-only form ship independently?
