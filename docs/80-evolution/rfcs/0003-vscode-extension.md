---
id: 0003-vscode-extension
title: "RFC-0003: VS Code extension (Phase 3)"
audience: explanation
tier: 2
status: draft
---

# RFC-0003: VS Code extension (Phase 3)

## Status

Draft. Target decision date: 2026-09-30.

## Summary

A VS Code extension that surfaces Irminsul findings inline as you edit, provides hover documentation for frontmatter fields, and exposes quick-fix actions for auto-fixable findings. The extension is a thin client over the existing CLI; it does not re-implement check logic.

## Motivation

The CLI delivers correct findings but imposes a context-switch: save, switch to terminal, run `irminsul check`, read output, switch back, find the line. For authors who spend most of their time in the editor, this friction adds up. An in-editor experience that shows findings as red/yellow underlines — identical to how editors surface TypeScript errors or ruff violations — removes the context-switch entirely.

Three specific pain points the extension addresses:

1. **Broken links and missing frontmatter** are discovered at commit time or in CI rather than while writing. Finding a broken link immediately after typing it is less costly than discovering it in a PR comment.
2. **Frontmatter is opaque.** Authors must remember the valid `audience` and `status` enum values. Hover tooltips and autocomplete remove this lookup.
3. **Fixable findings** (supersession, mtime-drift, etc.) require navigating to the file, opening it, and applying a one-line change. Quick-fix actions make this a single keystroke.

## Detailed Design

### Architecture

The extension is a **Language Server Protocol (LSP) server** wrapping the Irminsul CLI. This keeps the check logic in one place (Python) and makes the extension thin enough that a JetBrains port is feasible later.

```
VS Code Extension (TypeScript)
  ↕ LSP
Language Server (Python, ships with irminsul as `irminsul lsp`)
  ↕ in-process
DocGraph + Check registry (existing)
```

`irminsul lsp` is a new CLI subcommand (JSON-RPC over stdio) added in Phase 3. The extension starts it as a child process when a `.md` file is opened under a directory containing `irminsul.toml`.

### `irminsul lsp` subcommand

Implements a subset of LSP 3.17:

| LSP method | Irminsul behaviour |
|---|---|
| `textDocument/didOpen`, `didChange`, `didSave` | Re-run hard checks + soft checks on the changed file. Full graph rebuild on save (deferred rebuild for `didChange` with 500 ms debounce). |
| `textDocument/publishDiagnostics` | Emit one diagnostic per `Finding`. Severity mapping: `error → Error`, `warning → Warning`, `info → Information`. |
| `textDocument/hover` | Over a frontmatter key → show field description from `DocFrontmatter` schema. Over a link href → resolve and show target doc title. |
| `textDocument/codeAction` | For diagnostics with a `suggestion`, offer a quick-fix `WorkspaceEdit`. Powered by `irminsul fix --dry-run --format=json` (JSON output format from RFC-0001). |
| `workspace/didChangeWatchedFiles` | Re-run full graph rebuild when any `*.md` file changes outside the currently active editor (handles `irminsul new` writes, git checkout, etc.). |

LLM checks are **not** run by the LSP server (latency + cost). They are CLI-only.

### Extension features

**Diagnostics (always on):** hard check findings appear as red/yellow underlines with the check name as the source (`irminsul[frontmatter]`, `irminsul[links]`, etc.). Soft findings appear as yellow or blue info underlines.

**Hover:**
- Over `audience: howto` → tooltip: "How-to. A task-oriented guide that assumes the reader knows the goal and wants steps. Does not explain why."
- Over `last_reviewed: 2025-01-15` with a stale source → "Source files last modified 2025-03-22. Consider bumping last_reviewed."
- Over a relative link `[foo](../20-components/foo.md)` → shows first paragraph of `foo.md` frontmatter title + status.

**Autocomplete:**
- `audience:` → offers enum values with descriptions.
- `status:` → offers enum values.
- `describes:` list → offers glob completion scoped to detected `source_roots`.
- `depends_on:` → offers doc ids from the current graph.

**Quick-fix actions:**
- "Set status: deprecated" for supersession findings.
- "Bump last_reviewed to today" for mtime-drift findings.
- "Add missing children" for parent-child findings.

**Status bar item:** `✓ irminsul` (green, 0 errors) or `✗ irminsul (3)` (red, N errors). Click opens the Problems panel filtered to irminsul sources.

### Packaging

- Extension published to the VS Code Marketplace as `irminsul.irminsul`.
- The Python language server is **not bundled** inside the `.vsix`. Instead, the extension resolves the `irminsul` binary from the workspace's virtual environment (detected via `python.defaultInterpreterPath` or `which irminsul`). If not found, it shows a one-click "Install irminsul" action (`pip install irminsul` in the workspace terminal).
- Extension version is independent of the Python package version but tracks it: `0.3.x` extension requires `irminsul>=0.3.0`.

## Drawbacks

- **LSP adds a `lsp` subcommand to the CLI** that is only useful from editors. It increases the CLI surface area even though most users will never invoke it directly. Mitigation: document it clearly as "editor integration only."
- **Rebuilding the full graph on every save** can be slow on large doc trees. Initial implementation accepts this; a file-local re-check path (skipping the full walk) can be optimised in a follow-on.
- **Windows + Python virtual envs + PATH** is a known VS Code pain point. The extension must handle both `Scripts/irminsul.exe` (Windows venv) and `bin/irminsul` (Unix venv). The `python.defaultInterpreterPath` setting is the reliable lookup.

## Alternatives

- **Tree-sitter grammar + static parsing in TypeScript.** No Python subprocess, lower latency. Rejected: duplicates check logic; would immediately diverge from the CLI.
- **GitHub Actions annotation output** instead of an extension. Already planned for RFC-0001 (`--format=json` is a stepping stone). Not a replacement for in-editor feedback.
- **JetBrains plugin instead of (or alongside) VS Code.** The LSP architecture makes a JetBrains port straightforward once the language server exists; defer until VS Code version is proven.
- **Web-based doc dashboard** (show all findings in a browser UI). Complementary, not competing. Sprint 4+ scope.

## Unresolved Questions

- Should the extension manage a persistent language server process (one per workspace) or spawn a new process per check? Persistent is faster; per-process is simpler to implement. Start persistent; add restart-on-crash handling.
- How should the extension behave when `irminsul.toml` is absent? Options: silent (no diagnostics), offer to run `irminsul init`, show a one-time notification. Tentative: one-time notification with "Run `irminsul init`" button.
- Autocomplete for `describes:` globs requires knowing `source_roots` from config. Does the LSP server load config lazily on first request, or eagerly on workspace open? Eagerly is simpler; document that the extension requires `irminsul.toml` to be committed (not gitignored).
- Extension identifier: `irminsul.irminsul` (publisher.name) assumes a publisher account exists. Confirm publisher name before submitting to Marketplace.
