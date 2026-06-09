---
id: mcp-server
title: MCP server
audience: explanation
tier: 3
status: stable
summary: Read-only MCP stdio server that lets AI agents query the doc graph natively instead of shelling out to the CLI.
depends_on:
  - checks
  - cli
  - config
  - context
  - docgraph
  - new-list-regen
  - refs
  - surface
describes:
  - src/irminsul/mcp_server.py
tests:
  - tests/test_mcp_server.py
---

# MCP server

`irminsul mcp` serves the [DocGraph](../GLOSSARY.md#docgraph) to AI agents (Claude Code, Cursor, and any other MCP client) over the Model Context Protocol on stdio. Each tool is a thin wrapper over an existing query — [`context`](context.md), [`refs`](refs.md), the registered [`checks`](checks.md), `list`, and [`surface`](surface.md) — and returns the exact JSON string the corresponding CLI command prints with `--format json`. There is no new query engine and no new output shape to learn.

The server is strictly read-only: no tool writes files, and there is no MCP path to `fix`, `new`, `regen`, or `seed`. Config is re-read on every tool call, so a long-running server picks up edits between calls.

## Exposed tools

- `context_for_path(path)` / `context_for_topic(query)` / `context_changed()` — the three input modes of `irminsul context`: ownership, tests, dependencies, and relevant findings for a file, a topic, or the current git changes.
- `refs(target)` — backlinks for a doc id or path; if the target is not a doc, it falls back to symbol owner/reference lookup (the `--symbol` mode).
- `check(profile)` — runs the registered deterministic checks; only `hard` and `configured` are accepted, so LLM checks never run over MCP.
- `list_docs(kind)` — `orphans`, `stale`, `undocumented`, or `lifecycle`.
- `surface(kind, source_glob)` — derives a live code surface (`cli`, `http`, `exports`, `env-vars`, or a configured generic kind).

## Wiring it into an agent

The optional dependency comes from the `mcp` extra: `pip install 'irminsul[mcp]'`. Without it, `irminsul mcp` exits 1 with that install hint.

Claude Code:

```bash
claude mcp add irminsul -- irminsul mcp --path .
```

Any other MCP client, via the generic `mcpServers` shape:

```json
{
  "mcpServers": {
    "irminsul": {
      "command": "irminsul",
      "args": ["mcp", "--path", "."]
    }
  }
}
```

`--path` is resolved once at startup and points at the repo the server answers for; run one server per repo.

## Scope & Limitations

Read-only by design: agents that want to mutate the tree (scaffold docs, apply fixes, re-pin anchors) must run the CLI commands directly. Only stdio transport is supported — there is no HTTP/SSE listener, matching the no-server, no-hosted-state principle. LLM-backed advisory checks are excluded even if configured, so an MCP call can never spend API budget.
