---
id: 0024-anchored-prose-claims
title: Anchored prose claims (pinned provenance)
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
resolved_by: docs/50-decisions/0012-anchored-prose-claims.md
required_updates: []
---

# RFC 0024: Anchored prose claims

## Summary

RFC 0020 makes category-2 *intent* the doc's real content, and intent rots
silently. Add an opt-in inline marker that pins a paragraph to a specific code
symbol plus a content hash, and a deterministic `claim-anchor` check that flags the
claim when that symbol's code changes.

## Motivation

The existing deterministic catches on intent staleness are too blunt: `mtime-drift`
is file-level and clock-based (any edit to a described file trips every doc that
points at it); `claim-provenance` (RFC 0010) only covers structured frontmatter
claims in protected layers; `code-doc-cochange` (RFC 0021) is a PR-diff-time,
file-level nudge. None can say *"this specific paragraph's claim about this specific
symbol is now stale."*

## Detailed Design (as shipped)

A paragraph pins itself with an inline marker on the following line:

```markdown
The CLI is intentionally thin; logic lives in the modules it dispatches to.
<!-- anchor: src/irminsul/cli.py#check @sha256:1a2b3c -->
```

`file#symbol` is hand-written once; the `@<algo>:<hash>` pin is written and
refreshed by the re-pin command, never by hand. `#symbol` is optional (omit for a
file-level anchor) and supports dotted `Class.method`. The hash is taken over the
**AST-normalized** symbol body (`ast.unparse`), so formatting and comment churn do
not trip it — only a real change to the pinned code does.

The `claim-anchor` check (soft deterministic) reports, per marker:

- a missing file or symbol → **error** (the claim anchors at something that does not
  exist);
- a pinned hash that no longer matches → **warning** ("re-read and re-pin");
- an unpinned anchor → **info** (run re-pin to establish a baseline).

Adoption is opt-in: only paragraphs carrying a marker are checked. Un-anchored prose
stays on the coarse `mtime-drift` net — anchors are additive precision.

Re-pinning is a deliberate human acknowledgement that the prose was re-read and is
still true, exposed as `irminsul anchors --re-pin`. It is never performed
automatically by `irminsul fix`, which would rubber-stamp staleness and defeat the
check.

## Resolution

Accepted and implemented; resolved by
[`ADR-0012`](../../50-decisions/0012-anchored-prose-claims.md). The marker, the
check, and the `irminsul anchors` command ship together; irminsul dogfoods anchors
on its own intent paragraphs. Layering the hash pin over `mtime-drift` (rather than
replacing it) keeps coverage of un-anchored prose intact.
