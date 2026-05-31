---
id: 0012-anchored-prose-claims
title: "ADR-0012: Anchored prose claims"
audience: adr
tier: 2
status: stable
describes: []
summary: Pin intent paragraphs to code symbols with a content hash; flag drift deterministically.
---

# ADR-0012: Anchored prose claims

## Status

Accepted, 2026-05-30. Resolves [`0024-anchored-prose-claims`](../80-evolution/rfcs/0024-anchored-prose-claims.md).

## Context

After RFC 0020, the doc's real content is the non-derivable *why*, which rots
silently. The deterministic staleness catches are blunt: file-level mtime, protected
structured claims, and a PR-diff nudge. None can tell that a specific paragraph's
claim about a specific symbol has gone stale.

## Decision

Add an opt-in inline anchor marker that pins a paragraph to a code symbol plus an
AST-normalized content hash, a soft deterministic `claim-anchor` check (missing
target → error, drifted pin → warning, unpinned → info), and an `irminsul anchors`
command whose `--re-pin` is the explicit, human-driven acknowledgement. The hash pin
layers over `mtime-drift`; it does not replace it.

## Alternatives Considered

- **Time-based at symbol level.** Rejected: clock-based and trips on cosmetic edits;
  the AST-normalized hash is precise.
- **Auto re-pin during `irminsul fix`.** Rejected: silently re-pinning rubber-stamps
  staleness and defeats the check; re-pin is a deliberate command.
- **Anchors in frontmatter rather than inline.** Rejected: co-locating the pin with
  the claim keeps a prose edit and its re-pin together in review.

## Consequences

- Authors can make a specific intent claim deterministically self-checking.
- The hash must be refreshed (a cheap command) whenever the pinned code legitimately
  changes; this is the intended friction — it forces a re-read.
- Coverage stays opt-in; un-anchored prose is unaffected.
