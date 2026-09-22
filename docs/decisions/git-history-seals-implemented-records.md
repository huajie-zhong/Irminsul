---
id: git-history-seals-implemented-records
title: Git history seals implemented records
status: stable
describes: []
summary: An implemented RFC or an accepted decision is immutable because the protected branch's history says so, not because of a hash the author can recompute; frozen_hash is removed.
retires:
  - id: frozen-hash-seal
    kind: concept
    matches:
      - frozen_hash
      - frozen-content-changed
      - missing-frozen-hash
      - premature-frozen-hash
      - sealed-rfc-changed
    guidance: An implemented RFC is immutable once `main` records it as implemented; `diff-integrity` compares it with the merge base under `--diff`.
---

# Git history seals implemented records

## Status

Accepted, 2026-09-15.

## Context

[Change lifecycle](change-lifecycle.md) sealed an implemented RFC with `frozen_hash`, a hash
of the RFC stored in the RFC. `rfc-lifecycle` recomputed it and reported a mismatch. The
file vouched for itself: whoever edited the text could recompute the hash, and the check
passed.

`diff-integrity` already answers the question the hash could not. It reads the RFC as the
merge base recorded it, and a pull request cannot change what the protected branch
already holds. Against that, the hash adds nothing but a way to fake a seal.

Comparing with history also exposed two gaps. Deleting a sealed RFC, or renaming it and
editing it in the same change, passed, because the comparison skipped a file with no
copy on one side.

## Decision

- **History is the seal.** An RFC is implemented once the protected branch records
  `rfc_state: implemented`, which `irminsul change finalize` writes in the
  implementation's own pull request. `frozen_hash` is removed from the frontmatter
  schema, from finalization, and from `rfc-lifecycle`.
- **An implemented RFC does not change.** Under `--diff`, `diff-integrity` reports
  `implemented-rfc-changed` when an RFC that was implemented at the merge base differs,
  and `implemented-rfc-removed` when it no longer exists. An extension starts a new RFC.
- **An accepted decision is not removed.** `accepted-decision-removed` reports a decision
  record that was accepted at the merge base and no longer exists. Rewriting its
  `## Decision` section stays a hint.
- **A pure rename is not a change.** A record that is missing at its old path is not
  reported when a record at another path holds the same text apart from its `id`.
  Links to the old path break, and `links` reports them.
- **Parallel work never moves a sealed record.** Two branches that add records with the
  same name collide on the unsealed newcomer, which the later branch renames; the record
  the protected branch holds keeps its path and text.

## Alternatives Considered

- **Keep the hash beside history.** Rejected: a hash the author writes is not evidence,
  and two seals that can disagree need a rule for which one wins.
- **Seal in CI after merge.** Rejected: a bot committing to the protected branch after
  every merge adds an unreviewed commit, needs write access, and works on GitHub only.
- **Block every edit to an implemented RFC, including renames.** Rejected: a rename that
  keeps the text loses nothing, and broken inbound links are already reported.

## Consequences

- Immutability is enforced where a base exists: a pull request run with `--diff`, or a
  local `irminsul check --diff origin/main`. A plain local `check` does not notice an edit
  to an implemented RFC.
- Existing `frozen_hash` lines are ignored; nothing reads them.
- A repository that consolidates or wipes its records deliberately does so in a change a
  person merges past the failing check, or in a new history, as a reset does.
