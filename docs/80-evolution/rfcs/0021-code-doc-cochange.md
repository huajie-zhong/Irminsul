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

Surface a "you touched code but not its doc" co-change signal by **folding it
into the two surfaces that already resolve changed-source → owning-doc**, rather
than adding a new check. Specifically: (1) `irminsul context --changed` flags
every changed source whose owning doc is *not* itself in the change set, and
(2) `mtime-drift` gains an optional diff-aware mode for the CI path. No new
check, no new frontmatter field.

> **Revision note.** This RFC was originally drafted as a standalone soft check
> `code-doc-cochange` with two new CLI flags, three escape valves, and a
> `docs-frozen:` field. Review found ~90% of the work already existed in
> `_pending_for_changed` (`src/irminsul/context.py`) and that escape valves are
> over-engineering for a non-blocking signal. The design below is the descoped
> fold.

## Motivation

RFC-0018 tracks *declared* required updates: an accepted RFC names the docs it will
touch, and the queue surfaces unfinished work. But most code edits do not pass
through an RFC. When `src/irminsul/checks/links.py` changes, the doc that
`describes` it can sit untouched indefinitely. Today this is caught only by
`mtime-drift` after a configured threshold, and only if mtime configuration is
strict — a clock-based signal that cannot distinguish "edited today and
reviewed" from "untouched for months."

Agents and reviewers need a proactive signal: "this change touched code but not
its doc." It should be soft, not a gate, so it folds into existing surfaces
without blocking unrelated merges.

## What already exists

`irminsul context --changed` (`src/irminsul/context.py`, `_pending_for_changed`
at `context.py:255`) already does almost all of this:

1. computes the changed-file set (`_git_changed_paths`, `context.py:381` — note:
   `git status --porcelain`, i.e. **working-tree/index changes**, not a
   `base...head` range);
2. resolves each changed source path to its owning doc via the same `describes`
   glob resolution the hard `globs` and `uniqueness` checks use
   (`_ownership_for_source_path`, `context.py:342`);
3. groups changed sources under their owning doc, and adds the doc to that group
   *when the doc itself is in the change set* (`context.py:265-272`).

The only missing piece is reporting the gap: a group whose owning doc was **not**
among the changes. That is a few lines on top of existing infrastructure, not a
new check.

## Detailed Design

### 1. `context --changed` — the local/pre-commit surface (primary)

Add a per-group `doc_co_changed: bool` to the existing `_ChangedGroup` /
`_PendingResult` result (`context.py`). It is `True` when the owning doc's own
path appears in `_git_changed_paths`, `False` otherwise. The plain renderer
marks `False` groups ("owning doc not updated in this change"); `--format json`
exposes the boolean for agent consumption.

Because this reads the working tree, it catches drift *before commit* — earlier
than PR time — exactly where an agent already looks before finishing an edit. It
needs **zero new git plumbing**.

### 2. `mtime-drift` — the CI / maintenance-queue surface (secondary)

For the PR-diff path that reaches CI and the RFC-0018 queue, extend the existing
`MtimeDriftCheck` (`src/irminsul/checks/mtime_drift.py`) rather than adding a
parallel check. It already iterates per doc and resolves described sources
(`mtime_drift.py:33-48`).

Add two optional flags to `irminsul check`:

```text
irminsul check --profile configured --base-ref origin/main --head-ref HEAD
```

When both are supplied, `mtime-drift` additionally emits a diff-precise finding
for any doc whose described sources changed in `base...head` but whose own path
did not — a stronger signal than the clock threshold. When the flags are absent,
behavior is exactly today's clock-based check. The two flags are the only new
CLI surface, shared by (and justified for) the existing check.

### CI wiring

The composite Action sets `--base-ref ${{ github.event.pull_request.base.sha }}`
and `--head-ref ${{ github.event.pull_request.head.sha }}` on `pull_request`
triggers. On `push` to the main branch the flags are omitted, so `mtime-drift`
falls back to its clock signal.

### Strict mode

`--strict` promotes the diff-aware finding to a hard error along with the rest of
the soft deterministic set, giving projects a path to gate on doc co-change once
their authoring conventions settle.

### Deliberately deferred: escape valves

The original draft proposed `Doc-Impact:` commit/PR trailers, a per-glob
`docs-frozen: true` field, and a `docs-n/a: true` doc claim. **None ship in this
RFC.** A non-blocking signal does not need silencing — you read it or you do
not. Escape valves only earn their cost on a *gate*, so they are deferred to a
follow-up RFC scoped to the `--strict` promotion, where they can be designed
against real noise data. (The `docs-frozen:` field in particular mirrored the
`[tiers].generated` carve-out that RFC-0026 already retired, so it would have
shipped stale.)

## Relationship to Existing RFCs

- Diff-aware `mtime-drift` findings land in the maintenance queue defined by
  RFC-0018. Complementary: 0018 enforces what an accepted decision *declared*;
  this surfaces what a change *actually* touched without doc updates.
- Reuses the `describes` glob resolution already used by hard `globs` and
  `uniqueness`, and the changed-path resolution already in `context`.
- Consistent with RFC-0020 "derive, don't materialize": no new declared-intent
  frontmatter is introduced (the dropped `docs-frozen` / `docs-n/a` fields would
  have been exactly the kind of rot-prone cache 0020 removed).

## Drawbacks

The CI path requires git ref access. In hermetic CI without a base ref the
diff-aware finding is simply absent and `mtime-drift` reverts to its clock
signal — worth calling out so operators do not assume diff coverage they do not
have.

Folding two distinct signals (clock drift, diff co-change) into one check makes
`mtime-drift`'s output slightly less single-purpose. The shared per-doc owner
loop and the unified "doc lags its sources" intent make this an acceptable trade
versus a second near-identical check.

## Alternatives

- **Keep the standalone `code-doc-cochange` check (the original draft).**
  Rejected: it duplicates `_pending_for_changed` and answers the same "code
  moved, doc didn't" question as `mtime-drift`, paying for a parallel check plus
  escape-valve and frontmatter machinery the soft default does not need.
- **Make it a hard check by default.** Rejected: RFC-0018 chose a queue-based
  philosophy over a gate; a hard default conflicts. `--strict` is the opt-in.
- **`context --changed` only, no CI path.** Rejected: `context` is a local/agent
  command and does not run in the CI gate, so the RFC-0018 queue would never see
  the signal. The `mtime-drift` extension is what reaches CI.
- **Require explicit `co-changes:` frontmatter on every code-owning doc.**
  Rejected: the relationship is already encoded in `describes`.

## Unresolved Questions

- Many-to-one ownership: when several docs `describe` a changed file, must all of
  them co-change, or any one? `mtime-drift`'s per-doc loop already flags each
  owner independently, which suggests "each owning doc is evaluated on its own" —
  confirm this is the intended semantics for the diff-aware finding too.
- Should the diff use `git diff --name-only --find-renames` so a renamed source
  file is not seen as an add plus a delete?
- For multi-commit PRs, should the base be the merge base or the PR base SHA?
  The merge base is more accurate but slower; the PR base SHA is what GitHub
  provides directly.
