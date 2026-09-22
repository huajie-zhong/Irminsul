---
name: irminsul
description: Use when editing code or docs in a repo with an irminsul.toml at the root, before and after an edit, before committing, and whenever an irminsul check reports a finding.
---

Irminsul checks that docs agree with code. It never judges whether a sentence is true;
it proves what it can and points you at what needs reading. The full work order is in
`docs/guides/agent-protocol.md`.

## Read this first

The root `AGENTS.md` carries what a finding does and does not tell you, and the moves
that clear one while making the tree less true. Every harness loads it, and this
repository's `CLAUDE.md` imports it, so it is already in context — act on it rather than
re-deriving it. `docs/guides/agent-protocol.md` has the full procedure for working
through a finding.

Every finding has a class — certain (error), hint (warning or info), time (elapsed time
caused it). `irminsul explain <code>` describes any code.

## Before editing

- Run `irminsul orient`, then read `docs/AGENTS.md`.
- Run `irminsul context --before-edit <path...>` for the files you will touch: owning
  docs, recommended tests, active RFCs, dependencies. It runs no checks — its validation
  says `not_run` — so it is fast, and it is not a green light.
- Read the owning docs it names, and the decision records they link, before changing
  code; its excerpts are a map, not a substitute for them.
- Before renaming or moving anything, enumerate its inbound references first; `orient`
  names the query.
- Derive a code surface rather than trusting a doc's list of commands or options.

## After editing

- Run `irminsul context --after-edit`. It reports the repository's state and, separately,
  what this change introduced against a baseline. On a branch whose work is committed,
  pass `--base-ref origin/main`; without one it says the comparison did not run rather
  than reporting a zero it never measured.
- Run `irminsul list review --changed` (in a branch, `--base origin/main`). Re-read each
  listed sentence against the code it names, and correct the doc when it is wrong.
- For each `unbound` name it lists, run `irminsul anchors --suggest --doc <doc>`, pick the
  file that defines the name, and put `<!-- anchor: path#name -->` in that paragraph. If
  the name is not this repository's code, reword the sentence instead.
- Items marked `moved-file` are sentences an old owning doc still has about a file you
  moved to another doc; delete or rewrite them. A `stale-summary` item is a summary
  your body edit may have outdated.
- A `removed-sentence` item is an assertion your change deleted. Re-read it for anything
  the doc no longer says elsewhere, then justify the deletion: the behaviour is gone, or
  the sentence only repeated what a surface query, one file, or another doc already
  states, with no reason or gotcha of its own. Being inconvenient is not a reason.
- A `governing-claim` item is a claim whose evidence your change touched, queued even
  though you never opened its document. Read that document and the decisions it links,
  then answer the question `context` asked; `check` exiting 0 does not answer it. Under
  `governs-evidence` the question is whether the code still obeys the claim; under
  `review-on-divergence` it is which of the two is now wrong.
- Never remove or reword a `governs-evidence` claim because the code it governs changed:
  the claim wins, so the code is what to question. Change one only when the user decides
  to, with a decision record that names the claim.
- Run `irminsul fix` for mechanical remediations; pass `--confirm` only for held fixes
  you have read.

## Gates you must not work around

- `irminsul check` must exit 0 before committing. Plain `check` — `--delta` reports only
  what your uncommitted edits introduced and is not the gate.
- Never run `irminsul check --init-baseline` to get a green run. `--update-baseline`
  only removes entries that are already fixed.
- Do not edit an implemented RFC or delete an accepted decision record. Extend an RFC
  with a new RFC; replace a decision with a new ADR that supersedes it.
- A pull request runs `irminsul check --diff origin/<base>`, which also fails when the
  baseline grows, the adoption record grows, an implemented RFC changes, a sealed record
  is removed, a check or layer rule is turned off, or a doc stops describing code that
  is still there. Turn a check off only when the user asks, and record why in a decision
  record that names it.

## Pre-existing ownership debt

A repository that adopted Irminsul with undocumented code has an adoption record: the
finite list of files that had no owning doc that day. It excepts those files from the
ownership finding and nothing else — every check runs on them, and no check is waiting
to be switched on later.

- If `check` says files are still excepted, `irminsul list undocumented --all` marks
  which ones. They are work to do, not a passing grade.
- Editing a recorded file means documenting it in the same change:
  `diff-integrity/adoption-debt-touched` fails the pull request otherwise. The exception
  covers code nobody has gone back to, and you just did.
- Never add an entry to make a finding go away. `diff-integrity/adoption-record-grew`
  fails that, and it is the same move as widening a baseline. `--update-adoption` only
  retires entries whose file is now owned, deleted or moved.
- A record that still names a documented file is stale, not permission. The pull request
  reads ownership at the base, so taking an owner away is
  `diff-integrity/adoption-exception-revived` whether or not anyone ran
  `--update-adoption`. Restore the owner; do not reach for the record.
- Do not delete the record to clear anything, and do not adopt twice. The first record
  may only name files the base already held (`diff-integrity/adoption-debt-not-historical`),
  and deleting one that still holds entries is `diff-integrity/adoption-record-removed`.
- If the code lives in a separate repository, the record pins that repository's revision
  and every entry is checked against it. Never edit or move that pin to make a finding go
  away: `diff-integrity/adoption-source-rebound` fails it, and moving it forward turns
  everything the source gained since into debt. `uniqueness/adoption-source-unverifiable`
  means nobody can confirm the boundary — clone the source repository, or run
  `irminsul check --pin-adoption-sources` once for a record written before pins existed.
- CI needs full history (`fetch-depth: 0`). Without it the checks that read git find
  nothing and report nothing.

## Adding docs

- Before `irminsul new component --describes <path>`, check who owns the path with
  `irminsul context <path>`. Extend that doc instead of writing a second description.
  Split a doc only on purpose: pass `--split-from <doc-id>`, then remove the files from
  the old doc's `describes` and its prose.
- A new directory of code needs an owning doc in the same change; it does not escape
  coverage by being new.

## Recording decisions

- Draft proposals with `irminsul new rfc "Title"` and decisions with
  `irminsul new adr "Title"`; records are named by the slug of their title.
- Link a record instead of naming it. A sentence such as "we chose X" needs a link to
  the decision record in the same paragraph.
- Accepting an RFC and finalizing it are human decisions: run
  `irminsul change transition <id> accepted --confirm` or
  `irminsul change finalize <id> --confirm` only when the user has approved it.
