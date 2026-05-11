---
id: docgraph
title: DocGraph
audience: explanation
tier: 3
status: stable
depends_on:
  - config
  - frontmatter
describes:
  - src/irminsul/docgraph.py
  - src/irminsul/docgraph_index.py
tests:
  - tests/test_docgraph.py
  - tests/test_docgraph_index.py
---

# DocGraph

The DocGraph is the canonical in-memory representation of a repo's docs. `build_graph(repo_root, config)` walks `docs_root`, parses every `*.md`, and returns a graph indexed by id and by repo-relative path.

Three sidebands surface conditions checks need to report cleanly:

- `parse_failures` — files where YAML parsed but the schema rejected the result, or vice versa
- `missing_frontmatter` — files with no frontmatter at all (and not on the exemption list)
- `duplicate_ids` — `(id, first_path, conflicting_path)` tuples discovered during build

A small set of top-level filenames are exempt from the frontmatter requirement: [`README.md`](../README.md), [`GLOSSARY.md`](../GLOSSARY.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md). They're navigation, not doc atoms.

Paths stored on `DocNode` are repo-relative and POSIX-normalized so they're stable as dict keys and human-readable on Windows.

## Scope & Limitations

DocGraph does not check link targets — that is the `links` check's job. It does not parse source code or infer semantics from code structure. The graph is read-only once built; no check is allowed to mutate it.
