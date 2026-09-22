---
id: docgraph
title: DocGraph
status: stable
summary: The in-memory model of the docs tree that every check receives — what it holds, what it records instead of raising, and how data beyond the docs reaches a check.
depends_on:
  - config
  - frontmatter
describes:
  - src/irminsul/docgraph.py
  - src/irminsul/docgraph_index.py
  - src/irminsul/clock.py
owns_tests:
  - tests/test_docgraph.py
  - tests/test_docgraph_index.py
---

<!-- irminsul:ignore glossary-discipline/redefined-term reason="the component doc for the DocGraph, titled by its name" -->
# DocGraph

The DocGraph is the canonical in-memory representation of a repo's docs. `build_graph(repo_root, config)` walks `docs_root`, parses every `*.md`, and returns a graph indexed by id and by repo-relative path. It is the only input a registered check receives ([Architecture overview](../architecture/overview.md)), so anything a check needs to know — a diff's changed paths, the date to judge staleness by — reaches it through the graph.

A doc that cannot become a node does not stop the build. `build_graph` records it in one of the sideband fields on `DocGraph` — frontmatter that is not valid YAML or that the schema rejected, no frontmatter at all, or an id another doc already took — and the `frontmatter` check reports it. A doc whose id collided stays reachable by path but not by id: it is in `by_path` and absent from `nodes`, so code that iterates `nodes` never sees it.

A small set of top-level filenames are exempt from the frontmatter requirement: [`README.md`](../README.md), [`GLOSSARY.md`](../GLOSSARY.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`AGENTS.md`](../AGENTS.md) (validated by the `agents-manifest` check instead), and [`CLAUDE.md`](../../CLAUDE.md) (the Claude Code pointer, which only matters when `docs_root` is the repo root). They're navigation, not doc atoms, and the set is `EXEMPT_TOPLEVEL_NAMES`. Dot-directories under the docs root are not walked at all: they hold harness and tool state such as `.claude/`, `.git/`, and `.venv/`, which a repo-root `docs_root` would otherwise sweep in.

Paths stored on `DocNode` are repo-relative and POSIX-normalized so they're stable as dict keys and human-readable on Windows.

`DocNode.body` starts *after* the frontmatter block, but findings point at files. Any check that scans the body must translate through `DocNode.file_line(body_line)` rather than reporting the enumeration index, or its line numbers land inside the frontmatter. The offset is computed once at parse time (`ParsedDoc.body_offset`) because it is not a fixed function of the frontmatter's length — the parser also strips the blank run that follows the closing delimiter.

`build_graph` also accepts a `state_root` kwarg: the root for run-spanning on-disk state, such as the `external-links` HTTP cache. It defaults to the walked `repo_root` and differs only when the walked tree is disposable — [delta mode](baseline.md#delta-mode-check-delta)'s base pass walks a scratch `git worktree` while keeping `state_root` on the caller's real repository, so both passes of one run share a cache instead of re-fetching and discarding. A check that persists something across runs writes it under `state_root`; anything it reads from the tree under inspection comes from `repo_root`, or a delta run would judge the base revision by the working tree.

`build_graph` accepts an optional `now` kwarg that's stored on `DocGraph.now`; date-sensitive checks read it through the `clock.today(graph.now)` helper. The `--now YYYY-MM-DD` flag on `irminsul check` threads through to here; without it the system date is used.

Git history is read at most once per graph: `build_graph` discards the `git log` cached for an earlier graph, so a long-running process that builds a graph per call, such as the [MCP server](mcp-server.md), sees commits made between calls. A check that caches something derived from the repository must be bounded the same way ([context keeps no session](../decisions/context-keeps-no-session-external-checks-may-cache-observations.md)).

The CLI passes the paths changed in its diff range as `diff_changed_paths`, or leaves it `None` when no range resolved. A registered check that judges a change rather than the tree, such as `change-binding`, reads its changed set from there; `co-change` and the diff-integrity pass are not registered checks and take the range from the CLI directly.

`graph.source_map` is the one derived index that is *not* built during the walk. It resolves which repository and revision each managed file answers to, which costs a walk of the configured source roots, and most commands — `list`, `refs`, `new` — never ask. So it is built on first use and cached for the life of the graph, which is the right lifetime for the configuration (this graph's own object) and for the tree (what this graph walked), and the wrong one for the [adoption record](adoption-record.md), which the graph never reads: the map is rebuilt when a digest of that file changes. Its whole reason for existing on the graph is that there be one answer — see [where an entry is verified](adoption-record.md#where-an-entry-is-verified-decided-once).

Structured body sections are a graph concern, not a per-check regex ([Change lifecycle](../decisions/change-lifecycle.md)): `graph.requirements` holds the parsed `## Requirements` section (requirement blocks with stable ids, provenance, and WHEN/THEN scenarios, or the explicit no-new-behavior disposition) for every doc that has one, so the grammar check, transitions, and change reports share one line-accurate parser. Fenced code blocks are skipped, so a doc can quote the grammar without declaring requirements. The other derived indexes — backlinks, headings, and task lists — follow the same rule: `docgraph_index.py` builds each one once, with a pure builder, at the end of `build_graph`, and its module docstring names them and the code that reads them.

## Scope & Limitations

DocGraph does not check link targets — that is the `links` check's job. It does not parse source code or infer semantics from code structure.

Checks use the graph as read-only once it is built: `build_graph` fills every field and index before any check runs, and every check in a run reads the same graph object, so a check that wrote to it would change what later checks see. Nothing enforces this. `DocGraph` is a mutable dataclass; only `DocNode` is frozen.

We currently keep this module independent of individual checks, so the shared representation does not take on one check's behaviour and a check can be added or removed without the graph changing shape. That is a preference with a reason, not a rule: nothing enforces it and no claim declares it, so a concrete case that needs otherwise is a reason to revisit this paragraph, not to work around it. Weigh it before adding such an import, and say why in the change if you add one.
