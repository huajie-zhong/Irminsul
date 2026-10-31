---
id: a-change-is-judged-from-its-merge-base-to-the-working-tree
title: A change is judged from its merge base to the working tree
status: stable
describes: []
summary: A change runs from the merge base, read with its own configuration, to the working tree, unless `--committed-only` stops it at HEAD; a reviewed co-change warning is acknowledged by a commit trailer.
governs:
  - src/irminsul/checks/acknowledgement.py
  - src/irminsul/checks/change_range.py
  - src/irminsul/checks/co_change.py
  - src/irminsul/git/changes.py
  - src/irminsul/docgraph.py#ChangeRange
  - src/irminsul/config.py#parse_snapshot
  - src/irminsul/checks/diff_integrity.py#_owned_at_ref
---

# A change is judged from its merge base to the working tree

## Status

Accepted, 2026-10-28. Resolves
[Acknowledge a reviewed co-change or evidence drift](../rfcs/acknowledge-a-reviewed-co-change-or-evidence-drift.md).

## Context

A run that judges a change asks what the change touched and what the base meant. Ending the
change at `HEAD` would make an agent that may not amend learn each finding from a failed gate
after committing. The merge base is the one thing a change cannot rewrite, but only while it is
read on its own terms: one commit could delete an owning doc and add its test root to
`source_roots`, and read through the head's configuration the base's surviving declaration would
stop counting as ownership. Two hints are about a whole doc and carry no line, so no ignore
comment can answer them: `co-change/unreflected-change` and `claim-provenance/evidence-drift`.

## Decision

- **The working tree ends the range.** `check --diff <base>`, `--source-diff` in each source
  repository, `context --after-edit` once a base resolves, and the footprint of `change status`
  and `verify` compare the merge base of `<base>` and `HEAD` with the working tree: staged and
  unstaged edits, deletions, and untracked files gitignore does not exclude. On a clean tree
  that is `<base>...HEAD`, which CI sees; `--diff HEAD` is the uncommitted work. The before
  side is the merge base, for `new-dependency` and `list review --base-ref` too.
- **`--committed-only` means uncommitted work is not a change.** `check`, `context`,
  `change status`, `change verify` and `list review` accept it. The range ends at `HEAD`, files
  are compared as `HEAD` holds them, and history times are commit times; only the checks that
  judge the tree read the disk. With no base nothing is judged as a change, and the run says
  so: `context --after-edit` reports its change validation `not_run`, `list review --changed`
  prints the reason on stderr, and `change status` and `verify` report the `committed` baseline
  with no paths; `context --after-edit` treats a base it cannot resolve the same way.
- **`change finalize` refuses a dirty tree** ("Commit or stash first"), because uncommitted
  work names a change that does not exist yet.
- **A snapshot is judged by its own configuration.** A question about the merge base is
  answered with the base's `irminsul.toml` and adoption record: `_owned_at_ref` takes the
  configuration of the ref it reads, and the seal builds one `SourceMap` per side. The governing
  claim `adoption-exception-does-not-return` states the rule. The working tree is the one
  shared input, since a sibling repository is cloned into it once.
- **`co-change` asks for the doc:** under a diff range it warns on each owning doc whose claimed
  source changed or was deleted while the doc did not.
- **A commit trailer acknowledges a `co-change` warning.**
  `Irminsul-Reviewed: co-change/unreflected-change <doc path> reason="..."`, on a commit in the
  range, turns the warning into an info finding under its own code, quoting the required reason.
  A trailer covers changes up to its own commit, and uncommitted work is later than every commit,
  so the warning marks such a file `(uncommitted)`. A trailer that acknowledges nothing is
  `acknowledgement/unused`, an info finding, because a trailer cannot be removed without
  rewriting history. The suggestion prints the trailer to paste.
- **One step accepts trailers.** After classes are applied, the shared runner matches each
  `Irminsul-Reviewed: <code> <path> [<subject>] reason="..."` trailer of the change's commits to a
  finding by code, path and subject, accepts only a code declared `trailer`, and reports the
  accepted finding at info under its own code with the reason. A trailer that does not parse, or
  names a code not declared `trailer`, is `acknowledgement/invalid`, and one that matches nothing
  `acknowledgement/unused`, both at info. The co-change acknowledgement codes retire. A trailer
  stops covering a finding once a later commit, or uncommitted work, touches a file the finding
  is about.
- **A change that only moves pins does not update a doc for `co-change`** (accepted, not yet
  implemented), and `co-change` also reads the code repository's range given as
  `--source-diff`, answered by a trailer on a commit of that range.

## Alternatives Considered

- **End the range at `HEAD`.** Rejected: that is the failed gate after committing.
- **Add `git status` paths where a pass wants them.** Rejected: a second definition of the
  changed set.
- **Default to commits and add `--worktree`.** Rejected: the common local run is the dirty one,
  and CI cannot tell the two defaults apart.
- **Refuse `--committed-only` without a base.** Rejected: an empty range is a measured answer.
- **Read the base with the head's configuration.** Rejected: the change under review could edit
  what the base meant.
- **Report every configuration change that alters ownership.** Rejected: widening
  `source_roots` is the ordinary way to bring a tree under governance.
- **Let an earlier trailer cover a later edit.** Rejected: the edit was not re-read.
- **An ignore comment that matches findings with no line.** Rejected: it would outlive the one
  change a `co-change` warning belongs to.
- **Record reviewed hints in the baseline.** Rejected: the baseline holds certain findings for
  adoption, not reviews of hints.
- **Fold the diff signal into `mtime-drift`.** Rejected: a time threshold cannot tell a change
  that reached the doc from one that did not.

## Consequences

- One run before committing shows what the commit will trigger.
- A move without `git mv` reads as a deletion plus a new file until staged, partial staging
  commits a different change from the one judged, and a sibling repository's dirty work counts
  under `--source-diff`.
- Widening `source_roots` while deleting an owner is `diff-integrity/adoption-exception-revived`.
- Acknowledging is easier than editing; acknowledging before re-reading is one of the moves the
  root `AGENTS.md` names as making the tree less true. A pin covers a whole file, so narrowing
  the evidence is the remedy for a busy one.
- A hint about a whole doc rather than a line has no ignore comment to answer it: a trailer
  answers `co-change`, and a re-pin answers `evidence-drift`.
- A trailer's path and subject cannot contain whitespace, so a file with a space in its path
  cannot be named by a trailer, and its finding is answered by the fix.
- A trailer for a setting covers every entry under that dotted name: one naming `paths.sources.ref`
  accepts a ref change on every declared source.
- A hand edit inside a merge commit does not lapse a trailer, because merges do not count, so a
  reviewer reads the merge itself.

## Changes

- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  one step accepts commit trailers for every code declared to take one.
- 2026-10-29: Accepted [An edit with no base is judged against HEAD](../rfcs/an-edit-with-no-base-is-judged-against-head.md):
  `context --after-edit` with no base judges uncommitted work against `HEAD`.
- 2026-10-30: The trailer step is implemented: a finding whose code declares `trailer` is
  accepted by a trailer naming its path and subject, and the co-change acknowledgement codes
  retire.
