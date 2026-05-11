---
id: check-pipeline
title: Check Pipeline
audience: explanation
tier: 3
status: stable
describes: []
---

# Check Pipeline

How `irminsul check` flows from CLI invocation to exit code.

## Steps

1. **Resolve config** — `find_config()` walks upward from the invocation directory until it finds `irminsul.toml`. Exits 1 if none found.

2. **Build the DocGraph** — `build_graph(repo_root, config)` walks `docs_root`, parses every `*.md`, and produces a `DocGraph` with nodes indexed by id and by repo-relative path. Parse failures and missing frontmatter are collected as sidebands, not exceptions.

3. **Select checks** — the `--profile` flag determines which registries contribute checks:
   - `hard` — checks from `HARD_REGISTRY` that are enabled in config
   - `configured` — hard checks + enabled checks from `SOFT_REGISTRY`
   - `advisory` — configured checks + enabled checks from `LLM_REGISTRY`
   - `all-available` — all implemented deterministic checks regardless of config

4. **Run checks** — each check receives the full `DocGraph` and returns a list of `Finding` records. Checks run sequentially; the graph is not mutated between checks.

5. **Collect and sort findings** — all findings are merged and sorted by severity (errors first) then by path.

6. **Render output** — findings print one per line to stdout in `path  severity  [check]  message` format. Severity colors: red (error), yellow (warning), cyan (info). `--format json` emits a JSON array instead.

7. **Exit code** — exits 1 if any finding has `severity == error`; exits 0 otherwise. The `--strict` flag promotes warnings to errors.

## Scope & Limitations

This doc covers `irminsul check` only. The init, render, regen, and fix pipelines are not documented here. LLM advisory check details (budget tracking, caching) are in [`llm`](../20-components/llm.md).
