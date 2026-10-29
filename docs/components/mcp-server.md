---
id: mcp-server
title: MCP server
status: stable
summary: Read-only MCP stdio server that lets AI agents query the doc graph natively instead of shelling out to the CLI.
depends_on:
  - change
  - checks
  - config
  - context
  - docgraph
  - new-list-regen
  - orient
  - refs
  - surface
  - user-errors
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
      - change_status
      - change_verify
      - check
      - context_after_edit
      - context_for_path
      - context_for_topic
      - list_docs
      - orient
      - refs
      - surface
    omit: []
---

# MCP server

`irminsul mcp` serves the [DocGraph](../GLOSSARY.md#docgraph) to AI agents over the Model Context Protocol on stdio. Each tool wraps an existing query — [`context`](context.md), [`refs`](refs.md), [`checks`](checks.md), `list`, [`surface`](surface.md), [`orient`](orient.md), [`change`](change.md) — and returns the JSON the CLI command prints with `--format json`, so there is no new query engine and no new output shape. A tool's docstring is the description an agent sees; `irminsul surface mcp` lists them.

The server is strictly read-only: no tool writes files, and there is no MCP path to `fix`, `new`, `seed` or a lifecycle transition, because a write surface needs an explicit authorization model first.

Its own code is the one thing it cannot re-read. Python imported the `irminsul` package when the server started, so after a checkout moves or an upgrade replaces files it would keep answering from the modules it loaded, a mix of old and new that looks no different from a current answer. So it refuses instead: `code_fingerprint` records the package's `*.py` files when `create_server` runs, and every tool compares them through `stale_code_message` first. Refusing is the whole remedy; the server does not try to reload itself.

The refusal is the SDK's tool error because the SDK sends the agent only `Error executing tool <name>` for any other exception and keeps its text in the server's log. So the wrapper around every tool also turns every `UserError`, which the CLI's one handler prints as a message and an exit code, into a tool error carrying that text. Any other exception is a crash, and stays one.

## Wiring it into an agent

The server needs the `mcp` extra: `pip install 'irminsul[mcp]'`. Without it, `irminsul mcp` exits 1 with that hint. The harness spawns the `irminsul` it finds on its own PATH — not the one in a project virtual environment — so that install needs the extra: `pipx install 'irminsul[mcp]'`, or `pip install 'irminsul[mcp]'` into the interpreter on PATH. A harness typically surfaces a failed start only as a closed connection; run `irminsul mcp --path .` from the shell the harness starts from to see the hint.

That holds only while the console script itself starts. One left behind by an uninstalled package fails inside its own `__main__` before importing anything of ours, so it prints a `ModuleNotFoundError` traceback and no hint; the server never runs. Diagnose that case without the script (`python -c "import irminsul, irminsul.mcp_server"`), delete the stale script, and reinstall: `pipx install --force irminsul`, or `python -m pip install --force-reinstall 'irminsul[mcp]'` into the interpreter on PATH. `irminsul init` tries the launcher once with `mcp --probe` and warns when it cannot serve.

[Adoption](init.md) already writes this registration as `.mcp.json`; what follows is the fallback for a repo adopted without it, one whose `.mcp.json` was left untouched, or a client with its own config location.

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

Read-only by design: an agent that wants to mutate the tree (scaffold docs, apply fixes, re-pin anchors) runs the CLI directly. Only stdio is supported — there is no HTTP/SSE listener, matching the no-server, no-hosted-state principle.

The staleness guard fingerprints only the package's `*.py` files. A changed scaffold template or other package data, and an upgraded dependency such as the `mcp` SDK itself, do not trip it, and neither does a file replaced by one of the same size with its modification time restored.

The tool set is a [watched surface](../decisions/derive-facts-and-leave-meaning-to-the-reader.md): the `inventory:` block here is `complete: true`, so `inventory-drift` flags a tool added, removed or renamed in `mcp_server.py` until the list is updated. It checks names, not parity with the CLI read commands.
