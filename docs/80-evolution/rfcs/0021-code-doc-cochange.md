---
id: 0021-code-doc-cochange
title: Code-doc co-change drift signal
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0021: Code-doc co-change drift signal

## Summary

Add a soft deterministic check `code-doc-cochange` that, when given a base and
head git ref, emits a finding for every changed source file whose owning doc
was not also changed in the same range. Findings flow into the maintenance
queue from RFC-0018.

## Motivation

RFC-0018 tracks *declared* follow-ups: an accepted RFC names the docs it will
touch, and the queue surfaces unfinished work. But most code edits do not pass
through an RFC. When `src/irminsul/checks/links.py` changes, the doc that
`describes` it can sit untouched indefinitely. Today this is caught only by
`mtime-drift` after a configured threshold, and only if mtime configuration is
strict.

Agents and reviewers need a proactive signal: "this PR touched code but not
its doc." The signal should be soft, not a gate, so it can fold into the
existing queue without blocking unrelated merges.

## Detailed Design

### Inputs

```text
irminsul check --profile configured \
  --base-ref origin/main \
  --head-ref HEAD
```

Both flags are optional. When either is missing, the check skips. This keeps
local runs friction-free; the check is meaningful only against a diff.

### Algorithm

1. Compute the changed file set via `git diff --name-only base...head`.
2. For each changed path under a covered source root, resolve the owning doc
   by matching against `describes` globs across all docs.
3. If the owning doc is not in the changed set, emit a soft finding for that
   path naming the owning doc.

Findings include enough metadata for RFC-0018's queue to consume them
directly: changed path, owning doc id, owning doc path, reason
(`code-doc-cochange`).

### Escape valves

- Commit or PR trailer `Doc-Impact: n/a — <reason>`. Parsed from the merge
  commit message (`git log` between refs) or from a PR body when running in
  CI.
- Per-glob `docs-frozen: true` in `irminsul.toml`, matching the field
  introduced for generated source. Files under a frozen glob never trigger
  the check.
- Explicit `docs-n/a: true` claim on the owning doc itself, for code that is
  intentionally undocumented.

### CI wiring

The composite Action sets `--base-ref ${{ github.event.pull_request.base.sha
}}` and `--head-ref ${{ github.event.pull_request.head.sha }}` automatically
on `pull_request` triggers. On `push` to the main branch the check skips,
since the base ref is the previous commit and would mostly be noise.

### Strict mode

`--strict` promotes the finding to a hard error, giving projects a path to
gate merges on doc co-change once their authoring conventions are settled.

## Relationship to Existing RFCs

- Findings land in the maintenance queue defined by RFC-0018.
- Complementary to RFC-0018: 0018 enforces what an accepted decision
  *declared*; 0021 surfaces what a PR *actually* touched without doc updates.
- Reuses the `describes` glob resolution already used by hard `globs` and
  `uniqueness` checks.

## Drawbacks

The check requires git access. In hermetic CI without a base ref the check
skips silently, which is correct behavior but worth calling out so operators
do not assume coverage they do not have.

The escape valve via commit trailer requires reading the merge commit
message; for squash-merge workflows that drop trailers, the PR body fallback
is the only reliable path.

## Alternatives

- Make this a hard check by default. Rejected because RFC-0018 chose a
  queue-based philosophy over a gate-based one; a hard default would conflict.
- Detect via `mtime-drift` alone. Rejected because mtime cannot distinguish
  "edited today and reviewed" from "untouched for months"; the diff is the
  signal.
- Require explicit `co-changes:` frontmatter on every code-owning doc.
  Rejected because the relationship is already encoded in `describes`.

## Unresolved Questions

- Should the check use `git diff --name-only --find-renames` so a renamed
  source file does not falsely look like an add plus a delete?
- For multi-commit PRs, should the base be the merge base or the PR base
  SHA? The merge base is more accurate but slower; the PR base SHA is what
  GitHub provides directly.
