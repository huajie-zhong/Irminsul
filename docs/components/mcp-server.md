---
id: mcp-server
title: MCP server
status: stable
summary: Read-only MCP stdio server that lets AI agents query the doc graph natively instead of shelling out to the CLI.
depends_on:
  - change
  - checks
  - cli
  - config
  - context
  - docgraph
  - new-list-regen
  - orient
  - refs
  - surface
describes:
  - src/irminsul/mcp_server.py
owns_tests:
  - tests/test_mcp_server.py
inventory:
  - kind: mcp
    source: src/irminsul/mcp_server.py
    complete: true
    items:
      - anchors
      - binding_readiness
      - change_impact
      - change_status
      - change_verify
      - check
      - context_changed
      - context_for_path
      - context_for_topic
      - list_docs
      - orient
      - refs
      - surface
    omit: []
---

# MCP server

`irminsul mcp` serves the [DocGraph](../GLOSSARY.md#docgraph) to AI agents (Claude Code, Cursor, and any other MCP client) over the Model Context Protocol on stdio. Each tool is a thin wrapper over an existing query — [`context`](context.md), [`refs`](refs.md), the registered [`checks`](checks.md), `list`, and [`surface`](surface.md) — and returns the same JSON shape the corresponding CLI command prints with `--format json`. There is no new query engine and no new output shape to learn. The `check` tool differs from the CLI command in two ways: it runs only the enabled checks, and it applies no baseline or `--delta`, so findings a baseline suppresses in the CLI appear in its output.

The server is strictly read-only: no tool writes files, and there is no MCP path to `fix`, `new`, `regen`, or `seed`. Config and git history are re-read on every tool call, so a long-running server picks up edits and commits made between calls.

## Exposed tools

- `orient()` — the recommended first call in an unfamiliar repo: docs layout, doc counts, entry docs, configured checks, and the command vocabulary (see [orient](orient.md)).
- `context_for_path(path)` / `context_for_topic(query)` / `context_changed()` — the three input modes of `irminsul context`: ownership, tests, dependencies, and relevant findings for a file, a topic, or the current git changes.
- `refs(target)` — backlinks for a doc id or path; if the target is not a doc, it falls back to symbol owner/reference lookup (the `--symbol` mode).
- `check(profile)` — runs the enabled checks; only the `enabled` profile is accepted, and each finding carries its class.
- `list_docs(kind)` — `orphans`, `stale`, `undocumented`, `lifecycle`, or `review` (the marked review items only).
- `surface(kind, source_glob)` — derives a live code surface of any built-in or configured generic kind; `irminsul surface --help` names the built-ins.
- `anchors()` — the [anchored prose claims](anchors.md) report. Read-only: re-pinning an anchor remains a deliberate human acknowledgement through the CLI, never an MCP call.
- `change_status(change)` / `change_verify(change, base_ref)` / `change_impact(change, base_ref)` — the read side of the [bound-change lifecycle](change.md): state, evidence, blockers, semantic-review clues, and layered impact for one RFC. Each tool description names the confirmed CLI command to run next, because lifecycle mutation is deliberately not exposed over MCP — a write surface needs an explicit authorization model first.
- `binding_readiness()` — the pre-proposal baseline: error blockers, drift clues, and unrelated repository debt.

## Wiring it into an agent

The optional dependency comes from the `mcp` extra: `pip install 'irminsul[mcp]'`. Without it, `irminsul mcp` exits 1 with that install hint. The harness spawns the `irminsul` it finds on its own PATH — not the one in a project virtual environment — so that install is the one that needs the extra: `pipx install 'irminsul[mcp]'`, or `pip install 'irminsul[mcp]'` into the interpreter on PATH. The server's own exit is self-diagnosing, but a harness typically surfaces it only as a closed connection; run `irminsul mcp --path .` from the shell the harness starts from to see the hint. That advice holds only while the console script itself starts. A script left behind by an uninstalled package fails inside its own generated `__main__` before importing anything of ours, so it prints a `ModuleNotFoundError` traceback and no hint, and nothing this module could do would change that — the server never runs. Diagnose that case without the script (`python -c "import irminsul, irminsul.mcp_server"`) and repair it by reinstalling over the stale script. Initialization runs the launcher once and warns when it cannot serve, which is the one moment somebody is watching. It asks `irminsul mcp --probe`, not `--version`: a base CLI without the extra starts and prints its version quite happily, so `--version` came back clean on exactly the installation whose closed connection the probe exists to predict. `--probe` resolves the optional dependency and imports the server module, then exits without serving. An `irminsul` on PATH too old to know the flag is reported as being too old rather than guessed about — it may serve and it may not, and the newer install doing the asking cannot find out. The extra requires the 2.x MCP SDK — the server targets `mcp.server.MCPServer`, which replaced the 1.x `mcp.server.fastmcp.FastMCP`. The constraint is bounded below the next major so an upstream breaking rename fails at dependency resolution rather than at import.

[Adoption](init.md) already writes the project registration below as `.mcp.json`, so a scaffolded repo needs no manual wiring. What follows is the fallback: a repo adopted before the registration was scaffolded, one whose `.mcp.json` already existed and was therefore left untouched, or a client that reads its own config location.

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

`--path` is resolved once at startup and points at the repo the server answers for; run one server per repo. The scaffolded `.` relies on the harness starting the server in the project root, which Claude Code does for a project-scoped `.mcp.json`.

## Scope & Limitations

Read-only by design: agents that want to mutate the tree (scaffold docs, apply fixes, re-pin anchors) must run the CLI commands directly. Only stdio transport is supported — there is no HTTP/SSE listener, matching the no-server, no-hosted-state principle.

The tool set above is a [watched surface](../decisions/derive-dont-materialize.md): the `inventory:` block in this doc's frontmatter opts into completeness (`complete: true`), so the `inventory-drift` check keeps the declared tools honest against the live `@server.tool()` registrations — a tool added, removed, or renamed in `mcp_server.py` is flagged until the list is updated or the tool is added to `omit`. Governance is name-based and internal: it checks the doc's list against the registered tools, not parity with the CLI read commands.
