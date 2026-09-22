---
id: deterministic-enforcement
title: Deterministic enforcement
status: stable
describes: []
summary: Every check is deterministic; each finding's class decides whether it blocks, and baselines, deltas, co-change, and fixes shape how findings reach a team.
---

# Deterministic enforcement

## Status

Accepted, 2026-09-12.

## Context

A check that sometimes passes and sometimes fails on the same tree cannot gate a merge,
and a check that depends on a model's judgment cannot be argued with. Teams adopting
Irminsul on an existing codebase also need a way to stop new rot without first paying
off every old finding.

## Decision

- **Deterministic only.** Checks are graph operations, regular expressions, glob
  resolution, AST reads, and git arithmetic. No check calls a model; semantic review
  belongs to the reader or agent consuming Irminsul's output.
- **Classes decide what blocks.** Every finding carries a stable `<check>/<kind>` code
  that `irminsul explain` describes, and each code is certain, hint, or time, as
  [Finding classes decide what blocks](finding-classes-decide-what-blocks.md) records. Certain findings fail
  the run unless a baseline or `--delta` filters them out.
- **Adoption is ratcheted.** A baseline file that only shrinks records existing
  findings, and `check --delta` reports only findings new against a base revision.
- **Intent, not completeness, where code already knows.** `depends_on` and
  `requires_env` are checked for declarations the code contradicts, never for missing
  ones.
- **Claims carry provenance.** High-risk enforcement prose references structured claims
  whose evidence must fit their state; anchored paragraphs pin a symbol's normalized
  hash and are re-pinned only by a person.
- **Diff-aware ownership.** Given `--diff`, `co-change` warns for every owning doc whose
  claimed source changed, or was deleted, without the doc changing in the same range.
- **A change cannot lower its own gates.** Under the same range, `diff-integrity` reports a
  baseline that grew, an implemented RFC that changed or disappeared, and a rewritten or
  removed accepted decision, because each would let a change pass by editing what judges
  it ([Git history seals implemented records](git-history-seals-implemented-records.md)).
- **Fixes remediate findings, never guess.** A check may supply fixes only for findings
  it emits; edits that rewrite load-bearing content wait for `--confirm`.
- **One source policy.** Checks, reports, surfaces, and change analysis share one
  inventory: configured roots, repository `.gitignore`, explicit includes and excludes,
  and symlinks contained to the configured root.
- **Suppressions are audited.** A prose-file-reference exception that no longer hides
  anything is reported as stale and never baselined.

## Alternatives Considered

- **An LLM-backed advisory check.** Rejected: build correctness must not depend on model
  judgment; [Derive, don't materialize](derive-dont-materialize.md) hands semantic questions to an
  agent through a review queue instead.
- **Fold the diff signal into `mtime-drift`.** Rejected: a time threshold cannot tell a
  change that reached the doc from one that did not.
- **Use `git ls-files` or `git check-ignore` for inventory.** Rejected: source roots may
  sit outside git, and global excludes would make results machine-dependent.
- **Auto-re-pin anchors during fixes.** Rejected: re-pinning is the acknowledgement that
  someone re-read the prose.

## Consequences

- The same tree always yields the same findings, so CI results can gate merges.
- Checks miss what only reading can decide, which is why the review queue exists.
