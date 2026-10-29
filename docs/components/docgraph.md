---
id: docgraph
title: DocGraph
status: stable
summary: The in-memory model of the docs tree every check receives, and the one reader of fences and marked regions.
depends_on:
  - checks
  - config
  - frontmatter
  - surface
describes:
  - src/irminsul/docgraph.py
  - src/irminsul/docgraph_index.py
  - src/irminsul/fences.py
  - src/irminsul/marked_region.py
  - src/irminsul/clock.py
  - src/irminsul/source_tree.py
owns_tests:
  - tests/test_docgraph.py
  - tests/test_docgraph_index.py
  - tests/test_fences.py
  - tests/test_marked_region.py
  - tests/test_source_tree.py
---

# DocGraph

The DocGraph is the canonical in-memory representation of a repo's docs. `build_graph(repo_root, config)` walks `docs_root`, parses every `*.md`, and returns a graph indexed by id and by repo-relative path. It is the only input a registered check receives ([Architecture overview](../architecture/overview.md)), so anything a check needs to know — a diff's changed paths, the date to judge staleness by, which `--now` sets — reaches it through the graph.

A doc that cannot become a node does not stop the build. `build_graph` records it in a sideband field on `DocGraph` — frontmatter that is not valid YAML or that the schema rejected, no frontmatter at all, or an id another doc already took — and the `frontmatter` check reports it. A doc whose id collided is in `by_path` and absent from `nodes`, so code that iterates `nodes` never sees it. A doc that sets a retired frontmatter key still becomes a node: `DocNode.retired_fields` names the keys it set.
<!-- anchor: src/irminsul/docgraph.py#DocGraph.by_path @sha256:c06bfb81430b -->

`DocNode.body` starts *after* the frontmatter block, but findings point at files. Any check that scans the body must translate through `DocNode.file_line(body_line)` rather than reporting the enumeration index, or its line numbers land inside the frontmatter. The offset is computed once at parse time (`ParsedDoc.body_offset`) because it is not a fixed function of the frontmatter's length — the parser also strips the blank run that follows the closing delimiter.

A check that persists something across runs, such as the `external-links` HTTP cache, writes it under `state_root`; anything it reads from the tree under inspection comes from `repo_root`, or a delta run would judge the base revision by the working tree. The two differ only in [delta mode](baseline.md#delta-mode-check---delta), whose base pass walks a scratch `git worktree`.
<!-- anchor: src/irminsul/docgraph.py#DocGraph.state_root @sha256:f44252a113c4 -->
<!-- anchor: src/irminsul/docgraph.py#DocGraph.repo_root @sha256:9691f17adec9 -->

`graph.git` is a `GitReader` the graph owns ([Git helpers](git.md)), so a long-running process that builds a graph per call, such as the [MCP server](mcp-server.md), sees commits made between calls, and the base graph of delta mode reads its own history without discarding the working graph's. A check that caches something derived from the repository must be bounded the same way ([context keeps no session](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)).

`graph.change` is a `ChangeRange`, the diff range `check --diff` resolves, or `None` for a run that judges the tree alone. The type lives here as data and `checks/change_range.py` resolves it from git. Every pass that judges a change rather than the tree reads its range from here — the `co-change`, `diff-integrity` and `new-dependency` passes, which `checks/pipeline.py` runs exactly when the graph carries a range — so no two of them can be handed different ideas of what changed. The base pass of delta mode is built without one, so what those passes report is never counted as already there. `committed_only` is the one switch for leaving uncommitted work out, and a graph built with it, as the delta base graph always is, has no pending instant.
<!-- anchor: src/irminsul/docgraph.py#DocGraph.committed_only @sha256:f2bca604de9b -->
<!-- anchor: src/irminsul/docgraph.py#DocGraph.change @sha256:ff7335efed84 -->

`graph.source` is the graph's one snapshot of the configured source, a `SourceTree` created on first use and walked and surfaced once for the run, so every check reads one walk instead of walking for itself. It is not an init field, so `dataclasses.replace` cannot carry one graph's snapshot into another. A snapshot with a different configuration is a different tree: the base side `diff-integrity` reads with the base's configuration builds its own rather than borrowing this one.
<!-- anchor: src/irminsul/docgraph.py#DocGraph.source @sha256:f985074291e4 -->

`graph.source_map` resolves which repository and revision each managed file answers to, from the same walks. Most commands (`list`, `refs`, `new`) never ask, so it is built on first use and cached. It lives on the graph so that there is one answer: see [where an entry is verified](adoption-record.md#where-an-entry-is-verified-decided-once). The adoption record is likewise parsed once, as `graph.adoption_record`, with `graph.adoption_error` holding why an unreadable one is not there.

Structured body sections are a graph concern, not a per-check regex ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): `graph.requirements` holds the parsed `## Requirements` section of every doc that has one, so the grammar check, transitions, and change reports share one line-accurate parser. Every consumer skips fenced code through one reader, `src/irminsul/fences.py`, which depends only on the standard library so the anchor parser can share it. The text between a start and an end marker comment has one reader too, `src/irminsul/marked_region.py`, built on that fence reader, so `init`, `fix`, `agents-manifest`, `list review` and `retired-references` agree on which lines are a region and each words a malformed pair in its own terms. `docgraph_index.py` builds each derived index once, with a pure builder, at the end of `build_graph`. A body's markdown is parsed once (`DocNode.tokens`) and its links are read once (`DocNode.links`), then resolved by one rule, `resolve_href`, which is GitHub's. A heading is anchored by GitHub's rule too: `slugify` drops punctuation and turns each space into a hyphen without collapsing any, so `## Scope & Limitations` is linked as `#scope--limitations`, and `headings_of` numbers a repeated heading `-1`, `-2`. The README and the agent guides are not nodes, so `graph.guidance_files` holds each once for the run, with the root of the repository it lives in.
<!-- anchor: src/irminsul/fences.py#FenceTracker @sha256:311630bbca2e -->
<!-- anchor: src/irminsul/docgraph.py#DocGraph.requirements @sha256:5449f930ade6 -->
<!-- anchor: src/irminsul/docgraph.py#DocGraph.guidance_files @sha256:72b53e1c6d0a -->

## Scope & Limitations

DocGraph does not check link targets — that is the `links` check's job. The graph itself does not parse source code or infer semantics from code structure: `graph.source` reads and parses source files for the checks that ask, as a `SourceReader`, and keeps what it read for the life of the graph.

Checks use the graph as read-only: every check in a run reads the same graph object, and what the graph derives on first use, such as `source`, `claims` and `source_map`, is derived once for all of them, so a check that wrote to it would change what later checks see. Nothing enforces this. `DocGraph` is a mutable dataclass, while `DocNode`, `GuidanceFile` and `ChangeRange` are frozen.

The graph is kept independent of individual checks, so the shared representation does not take on one check's behaviour and a check can be added or removed without the graph changing shape. That is a preference with a reason, not a rule: nothing enforces it and no claim declares it, so a concrete case that needs otherwise is a reason to revisit this paragraph, not to work around it. Say why in the change if you add such an import. `src/irminsul/source_tree.py` is one: it walks with `walk_configured_source_files`, which lives in `checks/globs.py` beside the `globs` check that reports what the walk finds, because a second walker would be a second answer to which files are source. `DocGraph.claims` is the other: it reads `uniqueness.resolve_claims`, the one routine that matches `describes` patterns for ownership, so `uniqueness`, `globs`, `mtime-drift`, both import checks, `diff-integrity` and adoption read one claims table per graph instead of each matching every pattern again.
