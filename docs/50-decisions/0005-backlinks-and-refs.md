---
id: 0005-backlinks-and-refs
title: "ADR-0005: Add the refs backlink and symbol-reference query"
audience: adr
tier: 2
status: stable
describes: []
summary: Add `irminsul refs` as a CLI surface over the strong and weak inbound indexes plus claim and describes provenance.
---

# ADR-0005: Add the refs backlink and symbol-reference query

## Status

Accepted, 2026-05-14. Resolves
[`0014-backlinks-and-refs`](../80-evolution/rfcs/0014-backlinks-and-refs.md).

## Context

`DocGraph` already builds `inbound_strong` and `inbound_weak` indexes in
`src/irminsul/docgraph_index.py`, but the only consumer is `OrphansCheck`. An agent
or contributor asking "who references this doc?" or "which docs own this code
symbol?" had no direct surface — the data existed but was reachable only by writing
a check. RFC 0014 proposed `irminsul refs` to expose it as a stable query command,
with a doc-target mode for backlinks and a `--symbol` mode for blast-radius lookup
before a code rename.

## Decision

Add `irminsul refs` (`src/irminsul/cli.py`, `src/irminsul/refs.py`) as a read-only
query command with two mutually exclusive inputs:

- `irminsul refs <doc-id|path>` resolves the target by id or repo-relative path and
  returns two sections: **strong** references from `depends_on` frontmatter (via
  `graph.inbound_strong`) and **weak** references from Markdown body links (resolved
  relative to the source doc). Each hit carries source doc id, repo-relative path,
  and line number.
- `irminsul refs --symbol <name>` scans every node's `describes` globs and
  `claims.evidence` entries, returning **owners** (docs whose `describes` matches)
  and **references** (docs with a claim citing the symbol). Matching is
  case-insensitive substring, path basename/stem, or `fnmatch` glob.

Both modes support `--format plain|json` and `--path`. JSON shapes are
`{target, strong, weak}` for docs and `{symbol, owners, references}` for symbols.
Providing neither or both inputs exits 2 with `choose exactly one input`; an
unknown doc target exits 1.

`refs` is a pure query — it registers no check, has no profile, and never changes
exit code based on findings. It reads the `DocGraph` and nothing else.

## Alternatives Considered

- **Keep backlinks an internal `DocGraph` detail.** Rejected: agents and
  contributors need a stable, documented CLI surface for navigation and
  blast-radius checks, not a private index.
- **Fold this into `irminsul context`.** Rejected: `context` is task-oriented and
  returns a broad report; `refs` is a direct query with a compact, predictable
  output shape. Merging them would blur both surfaces.
- **A new check instead of a command.** Rejected: backlinks are a lookup, not an
  invariant — there is nothing to pass or fail.

## Consequences

- The `inbound_strong` / `inbound_weak` indexes now have a second consumer; their
  shape is effectively part of the CLI contract.
- Symbol mode's reach is bounded by what docs declare: it finds `describes` and
  `claims.evidence`, not arbitrary mentions in prose. A rename blast-radius check is
  only as complete as the provenance frontmatter.
- `refs` adds a query command but no check and no profile, so CI behaviour is
  unchanged.
