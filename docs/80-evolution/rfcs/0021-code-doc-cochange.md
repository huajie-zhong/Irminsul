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

Surface a "you touched code but not its doc" co-change signal on the two
surfaces that already resolve changed-source → owning-doc: (1) `irminsul context
--changed` flags every changed source whose owning doc is *not* itself in the
change set, and (2) `irminsul check --diff <base>` reports the same gap over a
git range for the CI path. No new frontmatter field.

> **Revision note.** This RFC was originally drafted as a standalone soft check
> `code-doc-cochange` with two new CLI flags, three escape valves, and a
> `docs-frozen:` field. Review found ~90% of the work already existed in
> `_pending_for_changed` (`src/irminsul/context.py`) and that escape valves are
> over-engineering for a non-blocking signal. The design below is the descoped
> fold.
>
> **As-shipped note.** The CI half landed as a standalone module
> (`src/irminsul/checks/co_change.py`) driven by a new `--diff` flag, *not* as a
> mode folded into `mtime-drift`. Detailed Design §2 below has been rewritten to
> describe what shipped; the reasoning for the divergence is in
> [Alternatives](#alternatives).

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

### 2. `check --diff` — the CI / maintenance-queue surface (secondary)

The PR-diff path that reaches CI and the RFC-0018 queue ships as
`src/irminsul/checks/co_change.py`, a standalone module deliberately kept
**outside all three registries**. A registered `Check` receives only a
`DocGraph`; this signal additionally needs the changed-file set from `git diff
<base>...<head>`, which only the CLI can supply. Registering it would mean either
smuggling diff state onto the graph for one consumer or listing a check in
`irminsul.toml` that silently no-ops on every run without a diff flag. So the
CLI calls `run_co_change(graph, changed)` directly and folds its findings into
the normal sort/print/JSON/summary pipeline:

```text
irminsul check --diff origin/main
irminsul check --base-ref origin/main --head-ref HEAD   # equivalent, older spelling
```

Ownership resolution reuses `resolve_claims` / `most_specific_claims` from the
`uniqueness` check, so "who owns this file?" has exactly one answer across the
tool. Claims resolve against the changed set directly rather than a full source
walk, which also means a *deleted* claimed file still enforces on its owning doc.
Findings are grouped one-per-owning-doc, listing every changed-but-unreflected
file it claims.

`mtime-drift` keeps only its clock signal; the diff-precise finding it briefly
carried was removed rather than duplicated.

### CI wiring

`--diff <base>` is the flag CI templates: on `pull_request`, `--diff ${{
github.event.pull_request.base.sha }}`. `--base-ref`/`--head-ref` remain as the
two-flag spelling. On `push` to the main branch the flags are omitted and no
co-change finding is produced.

### Strict mode

`--strict` promotes the co-change warning to an error along with the rest of the
soft deterministic set, giving projects a path to gate on doc co-change once
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

- Co-change findings land in the maintenance queue defined by RFC-0018.
  Complementary: 0018 enforces what an accepted decision *declared*; this
  surfaces what a change *actually* touched without doc updates.
- Reuses the `describes` glob resolution already used by hard `globs` and
  `uniqueness`, and the changed-path resolution already in `context`.
- Consistent with RFC-0020 "derive, don't materialize": no new declared-intent
  frontmatter is introduced (the dropped `docs-frozen` / `docs-n/a` fields would
  have been exactly the kind of rot-prone cache 0020 removed).

## Failure semantics

The CI path requires git ref access, and the two spellings fail differently on
purpose:

- **`--diff <base>` fails loudly (exit 2).** An empty or unresolvable base ref
  exits 2 with a message that distinguishes "no git repository with commit
  history here" from "that ref does not resolve". `--diff` is an explicit opt-in
  gate, and a gate whose diff cannot be computed is a gate that never fires: it
  would report zero findings and exit 0, which is indistinguishable from a clean
  run. That silent pass is the failure mode worth spending an exit code on — an
  empty ref is the common shape of it, since a workflow templating `--diff ${{
  github.base_ref }}` interpolates to the empty string on `push` events.
- **`--base-ref`/`--head-ref` degrade gracefully.** They predate the gate and are
  used by pipelines that expect the run to continue; an unresolvable ref (a
  shallow `actions/checkout` clone that never fetched the base sha, a tarball
  checkout with no history) prints a yellow stderr warning, skips the co-change
  signal, and reports the remaining findings normally. An *empty* value is still
  exit 2 — that is a malformed invocation, not a hostile environment.

So "in hermetic CI without a base ref the finding is simply absent" holds for the
older flags, and operators who want the stronger guarantee opt into `--diff`.

## Drawbacks

The signal lives outside the check registries, so it is not selectable from
`irminsul.toml` and does not appear in `--profile` listings — it is reachable
only through the CLI flags. That is the cost of the input it needs (see
Detailed Design §2); the mitigation is that its findings are otherwise
indistinguishable from a soft check's, including `--strict` promotion.

## Alternatives

- **Fold the diff signal into `mtime-drift` (what this RFC first specified).**
  Not shipped. The fold saved a file but not the machinery: a registered check
  sees only the `DocGraph`, so the changed-path set had to be smuggled onto the
  graph as a field that exactly one check read and every other consumer ignored.
  It also welded two signals with different inputs (a clock threshold; a git
  range) and different lifetimes into one check whose output no longer said
  which one fired. The standalone module keeps `mtime-drift` single-purpose,
  keeps the graph free of per-invocation diff state, and still reuses the
  ownership resolution — which was the actual duplication worth avoiding.
  Registering it as a normal soft check was likewise rejected: it would sit in
  `irminsul.toml` no-opping on every run that lacks a diff flag.
- **Keep the escape valves from the original draft** (`Doc-Impact:` trailers,
  `docs-frozen:`, `docs-n/a:`). Still rejected, unchanged — see *Deliberately
  deferred* above.
- **Make it a hard check by default.** Rejected: RFC-0018 chose a queue-based
  philosophy over a gate; a hard default conflicts. `--strict` is the opt-in.
- **`context --changed` only, no CI path.** Rejected: `context` is a local/agent
  command and does not run in the CI gate, so the RFC-0018 queue would never see
  the signal. The `mtime-drift` extension is what reaches CI.
- **Require explicit `co-changes:` frontmatter on every code-owning doc.**
  Rejected: the relationship is already encoded in `describes`.

## Unresolved Questions

Resolved during implementation:

- **Many-to-one ownership.** Settled as "any one owner suffices": a changed
  source file is unreflected only when *none* of its most-specific owning docs
  changed in the same diff. Findings are then grouped per owning doc, so each
  owner still gets its own finding listing its own files.
- **Renames.** Yes — the diff runs `git diff --name-only --find-renames`, so a
  renamed source file appears once at its destination rather than as an add plus
  a delete.
- **Merge base vs. PR base SHA.** The three-dot range (`<base>...<head>`), i.e.
  the merge base. A two-dot range against a moving PR base attributes unrelated
  commits from the target branch to the PR.

Still open:

- Whether `--strict` co-change gating produces tolerable noise on real repos, and
  therefore whether the deferred escape valves ever need to ship.
