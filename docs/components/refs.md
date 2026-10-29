---
id: refs
title: Refs backlink query
status: stable
summary: The docs that depend on or link to a doc, from the current DocGraph.
depends_on:
  - checks
  - docgraph
  - frontmatter
  - user-errors
describes:
  - src/irminsul/refs.py
owns_tests:
  - tests/test_cli_refs.py
  - tests/test_refs_unit.py
---

# Refs backlink query

`irminsul refs <doc-id|path>` returns the docs that depend on or link to a doc, from the current [DocGraph](docgraph.md): **strong** references from `depends_on`, `implements` and `resolved_by` frontmatter (via `inbound_strong`), **weak** ones from Markdown body links. A `resolved_by` hit's line is 1: the decision record it names never names the target back, so its own frontmatter holds no line for the edge. A target that names no doc exits 2.
<!-- anchor: src/irminsul/docgraph.py#DocGraph.inbound_strong @sha256:5adf99e9515e -->

It answers for docs only: a code name has no backlink index, so the docs that mention one are found by searching the tree, and a path's owning doc and governing claims by `irminsul context <path>` ([Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)).

## Scope & Limitations

A rename blast-radius result is only as complete as the frontmatter and links it reads: a doc named only in prose returns nothing.
