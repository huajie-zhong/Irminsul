---
id: 0014-backlinks-and-refs
title: "RFC-0014: Backlinks and symbol-reference query"
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0014: Backlinks and symbol-reference query

## Summary

Add `irminsul refs` as a CLI surface for doc backlinks and symbol-reference
lookups, using the strong and weak inbound indexes already built by `DocGraph`.

## Motivation

`DocGraph.inbound_strong` and `DocGraph.inbound_weak` are built in
`src/irminsul/docgraph_index.py`, but they are consumed only by `OrphansCheck`.
Agents asking who references a doc or symbol have no direct surface.

## Detailed Design

Add a refs command:

```text
irminsul refs <doc-id|path>
```

For a document target, plain output is a two-section list:

- Strong references from `depends_on`.
- Weak references from Markdown links.

Each result includes the source doc id and line number. JSON output uses this
shape:

```json
{
  "target": "...",
  "strong": [],
  "weak": []
}
```

Add a symbol lookup mode:

```text
irminsul refs --symbol <name>
```

Symbol mode scans `claims.evidence` and `describes` globs, then returns docs
that own or reference the requested symbol. The intended use case is
blast-radius lookup before renaming code symbols.

## Alternatives

- Keep backlinks as an internal `DocGraph` detail. Rejected because agents and
  contributors need a stable CLI surface for navigation and blast-radius
  checks.
- Fold this into `irminsul context`. Rejected because references are a direct
  query with a compact output shape, while context remains task-oriented.
