---
id: refs
title: Refs backlink and symbol query
audience: explanation
tier: 3
status: stable
depends_on:
  - docgraph
describes:
  - src/irminsul/refs.py
tests:
  - tests/test_cli_refs.py
---

# Refs backlink and symbol query

`irminsul refs` returns doc backlinks and symbol references from the current [DocGraph](docgraph.md). It is a read-only runtime query: no check, no profile, no findings-driven exit code.

The command takes exactly one input:

- `irminsul refs <doc-id|path>` resolves the target by id or repo-relative path and returns **strong** references from `depends_on` frontmatter (via `inbound_strong`) and **weak** references from Markdown body links. Each hit carries source doc id, repo-relative path, and line number.
- `irminsul refs --symbol <name>` scans every node's `describes` globs and `claims.evidence` entries, returning **owners** (docs whose `describes` matches) and **references** (docs with a claim citing the symbol). The intended use is blast-radius lookup before renaming a code symbol.

Both modes support `--format plain|json` and `--path`. Providing neither or both inputs exits 2; an unknown doc target exits 1.

The decision and rejected alternatives are recorded in [ADR-0005](../50-decisions/0005-backlinks-and-refs.md), resolving [RFC-0014](../80-evolution/rfcs/0014-backlinks-and-refs.md).

## Scope & Limitations

Symbol matching is case-insensitive substring, path basename/stem, or `fnmatch` glob — it finds declared `describes` and `claims.evidence`, not arbitrary mentions in prose. A rename blast-radius result is only as complete as the provenance frontmatter. Weak references are resolved by parsing Markdown links relative to the source doc; non-doc and external links are ignored.
