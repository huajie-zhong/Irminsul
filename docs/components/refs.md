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

`irminsul refs <doc-id|path>` lists every place to edit before a doc is renamed or removed, from the current [DocGraph](docgraph.md). **Strong** references are the docs whose frontmatter names the target in `depends_on`, `implements` or `resolved_by` (via `inbound_strong`), each at the line of that entry, or of the `resolved_by` key; an RFC that names a decision record in `resolved_by` is therefore listed under the record. **Weak** ones are the Markdown links that resolve to the target's path, whether they sit in a doc or in a guidance file such as the root `AGENTS.md` or `docs/AGENTS.md`; a guidance file has no id, so its hit carries a null `doc_id`. A guidance file can be the target as well, by its repo-relative path: it has no frontmatter, so it has no strong references, and the report's `target` is its path rather than an id. A target that names neither a doc nor a guidance file exits 2.
<!-- anchor: src/irminsul/docgraph.py#DocGraph.inbound_strong @sha256:5adf99e9515e -->
<!-- anchor: src/irminsul/refs.py#RefHit.doc_id @sha256:867a78b4f4aa -->
<!-- anchor: src/irminsul/refs.py#DocRefsReport.target @sha256:17a246bd40b9 -->

It answers for docs and guidance files only: a code name has no backlink index, so the docs that mention one are found by searching the tree, and a path's owning doc and governing claims by `irminsul context <path>` ([Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)).

## Scope & Limitations

A rename blast-radius result is only as complete as the frontmatter and links it reads: a doc named only in prose returns nothing. It reads the docs and the guidance files, so a link in Markdown outside both, such as `CHANGELOG.md`, is not found.
