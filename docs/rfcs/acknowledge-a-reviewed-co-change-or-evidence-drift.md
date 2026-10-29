---
id: acknowledge-a-reviewed-co-change-or-evidence-drift
title: "Acknowledge a reviewed co-change or evidence drift"
status: stable
describes: []
rfc_state: implemented
weight: large
affects:
  - checks
  - anchors
  - frontmatter
  - git
  - cli
  - init
  - surface
resolved_by: docs/decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md
required_updates: []
---

# Acknowledge a reviewed co-change or evidence drift

## Summary

A reader who re-reads a doc and finds it still right can record that, instead of editing the
doc just to clear a hint, a finding that asks for judgment. The co-change warning and evidence
drift carry no line for an ignore comment to reach, so this [RFC](../GLOSSARY.md#rfc) gives
each an acknowledgement that lasts as long as its finding: a reasoned commit trailer for the
one change a co-change warning belongs to, and a pinned hash of a claim's evidence, written by
the existing `--re-pin` command, until that evidence changes again. Three decisions, all
settled; none waits for the owner.

## Problem

A worked example from this repository:

1. A branch rewrites one sentence of the scaffolded agent-protocol template,
   `src/irminsul/init/scaffolds/docs/guides/agent-protocol.md.j2`.
2. `docs/components/init.md` claims `src/irminsul/init/**` and did not change, so
   `irminsul check --diff main` gives it the co-change warning: a file it claims changed and
   it did not.
3. A reader checks `init.md` and finds nothing stale: it describes what init writes, not the
   protocol's wording.
4. The warning still clears only when `init.md` changes, and by design a whitespace-only edit
   does not count, so the edit must say something new whether or not anything true is left to
   add. An ignore comment would be that edit, and would outlive the change, never reported as
   unused.

Evidence drift, a claim's evidence committed after its doc, has the same shape and fires more
often. Three claims cite all of `src/irminsul/cli.py`, so a commit that changes only the
`anchors --suggest` output drifts all three. Each can be re-read and found true, nothing
records that it was, and only a commit to both of their docs clears them.

Under `--strict`, the adopter-facing Action's `strict` input, either hint then forces a filler
edit into a correct doc: the gaming the decision on what blocks set out to prevent.

## How it works

**A trailer acknowledges one change's warning.** A commit may end its message with an
`Irminsul-Reviewed` line naming the check, the doc and a required reason. In a run given a diff
range, that doc's co-change warning becomes an info finding quoting the reason, so the pull
request shows what was waved through and why. A trailer covers only the changes up to its own
commit and leaves nothing in the tree once the change merges.

**A pin acknowledges a claim until its evidence changes.** The re-pin command, which already
records that a doc's anchors were re-read, also writes a hash of each evidence file of every
claim in the doc. While a file keeps that hash, drift is not reported for it; once it differs,
today's comparison of commit times applies, so a pin only ever removes drift.

**Two mechanisms, because the findings differ.** A co-change warning belongs to one change and
should vanish with it; a review of evidence stays true until the evidence moves.

Not chosen: an ignore comment that matches findings with no line, the baseline, narrowing
evidence to a symbol, a trailer for drift too, and leaving both as they are.

## Cost and risk

An acknowledgement is easier than an edit; the required reason, shown on every run that
honours it, is the bargain ignore comments already make. A trailer stays in history, so in a
stack of branches one can go unused and be reported from then on, as info, so nothing blocks.
Pins add a frontmatter field that changes on every re-pin, which makes claim blocks noisier in
diffs.

## Decisions

The three questions the draft opened with, all settled:

1. **One trailer key.** Every per-change acknowledgement is `Irminsul-Reviewed: <check> ...`,
   so a later diff-only hint adds a check name, not a new trailer.
2. **`irminsul fix` stays out of re-pinning.** A pin says someone re-read the claim, which no
   remediation can say for them; the drift suggestion names the command instead.
3. **The finding carries the trailer to paste**, its doc's path filled in, so every report of
   the finding, CI annotations included, shows it without a second command.

## Design detail

### The two hints

The hints are `co-change/unreflected-change` and `claim-provenance/evidence-drift`. Neither
carries a line, so no ignore comment reaches it.

[Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md) says
an agent resolves a hint "by investigating, then fixing the doc or leaving a reasoned ignore
comment for a reviewer." That second path does not exist for these two hints. The class
decision rejected blocking on hints for exactly this reason: "some hints have no honest fix
when the doc is right, so blocking on them teaches an agent to game the signal."

`evidence-drift` compares the last commit of each evidence file with the last commit of the
doc. The three claims that cite all of `src/irminsul/cli.py` are `action-adds-no-logic` in
`docs/architecture/overview.md`, and `hints-advise` and `fix-remediation-available` in
`docs/foundation/enforcement.md`.

### A trailer acknowledges one change's co-change warning

A commit message may carry, in its trailer block:

```text
Irminsul-Reviewed: co-change docs/components/init.md reason="describes what init writes; the template wording is not in it"
```

The value mirrors an ignore comment: the check or code, the doc by id or repo-relative
path, and a required `reason`. Under `--diff <base>`, the run reads the trailers of the
commits between the merge base and `HEAD`. A `co-change` warning on a doc that a valid
trailer names is not reported as a warning. It is reported as an info finding,
`co-change/acknowledged`, that quotes the reason, so the pull request's annotations show
what was waved through and why, as the baseline shows what it hides.

- The trailer names the check, `co-change`, or its code, `co-change/unreflected-change`,
  as an ignore comment may.
- A trailer covers the changes made up to its own commit. A later commit that changes one
  of the doc's files was not re-read against it, so the warning stands until a later
  trailer answers it.
- A trailer without a reason, naming no doc, or for any other check acknowledges nothing,
  and neither does one naming a doc `co-change` does not warn on. Each is reported as
  info. An unused ignore comment is an error because deleting it is the fix; a commit
  trailer cannot be deleted without rewriting history, so a warning about one would be a
  finding nobody can clear, which `--strict` would fail on forever.
- A run without `--diff` reads no trailers: `co-change` does not run there.

The acknowledgement lives exactly as long as the finding. It is scoped to the commits
the pull request adds, a reviewer reads it in the commit list, and it leaves nothing in
the tree once the change merges. It is read from git, so it is deterministic and needs no
stored state.

### A pin acknowledges a claim's evidence until it changes again

A claim may record the hash of each evidence file as it was when someone last checked the
claim against it:

```yaml
claims:
  - id: action-adds-no-logic
    evidence:
      - action.yml
      - src/irminsul/cli.py
    pinned:
      action.yml: sha256:3f2a9c1b7d04
      src/irminsul/cli.py: sha256:b81e0c44a9d2
```

`irminsul anchors --re-pin --doc <doc>` already asserts "I re-read this doc and it is
still true" for the doc's anchors and inventory fingerprints. It also writes `pinned` for
every claim in that doc. While an evidence file still has its pinned hash,
`evidence-drift` does not report it, whoever committed what. Once the hash differs, the
file falls back to today's commit-time comparison, as does an evidence file without a
pin. A pin therefore only ever removes drift: updating the doc beside the evidence still
answers it, a hash that differs on another Python version costs nothing, and no existing
repository changes behavior until it re-pins. A pin on a path the claim no longer cites
is ignored and dropped by the next re-pin rather than rejected, because a doc that fails
to parse is out of reach of the re-pin that would repair it.

The hash normalizes the file the way an anchor does: a Python file through its syntax
tree, any other file with whitespace collapsed. A formatting-only commit therefore does
not drift a claim.

Re-pinning is an edit to the doc and appears in the diff. Unlike filler it records a
fact, which evidence version the claim was checked against, and `--re-pin` refuses to
sweep the repository without `--all`, so it stays a per-doc statement.

### Limits of a trailer

- In a stack of branches, a trailer written on the upper branch for a change the lower
  branch made goes unused once the lower one merges, and is reported as unused from then
  on; it is info, so nothing blocks.
- A trailer is invisible to a run without a diff range, and a squash merge may drop it.
  Neither matters: `co-change` runs only with a range, and after merge the finding is
  gone.

### Alternatives not chosen

- **An ignore comment that matches findings with no line.** Rejected: it lives in the doc
  forever while the `co-change` finding lasts one change, it would silence future real
  warnings on that doc, and adding it already satisfies `co-change`, so it proves
  nothing.
- **Put the evidence in the baseline.** Rejected: the baseline holds certain findings
  only and exists for adoption, not review
  ([A baseline holds certain findings and grows only by decision](../decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md)).
- **Narrow each claim's evidence to a symbol, such as `cli.py#check`.** Useful, and
  compatible with this RFC, but it reduces how often drift fires rather than giving a
  way to acknowledge it, and narrowing evidence to clear a finding is one of the moves
  `AGENTS.md` names as making the tree less true.
- **A trailer for `evidence-drift` too.** Rejected: that finding runs without a diff
  range, where no trailers are read, and it describes the doc's state rather than a
  change.
- **Leave both as they are.** Rejected: under `--strict` it forces filler edits, which is
  the gaming the class decision set out to prevent.

## Requirements

### Requirement: Trailer acknowledges co-change
ID: trailer-acknowledges-co-change
Provenance: code

A `co-change` warning on a doc SHALL NOT be reported as a warning when a commit in the
diff range carries an `Irminsul-Reviewed: co-change <doc> reason="..."` trailer naming
that doc with a non-empty reason, unless a later commit in the range changed one of the
files the warning lists, and SHALL be reported as an info finding that quotes the reason.

#### Scenario: Reviewed doc
- **WHEN** a branch changes a file `docs/components/init.md` claims, leaves `init.md` unchanged, and one of its commits carries a valid trailer naming `init.md`
- **THEN** `irminsul check --diff <base> --strict` reports `co-change/acknowledged` for `init.md` and does not fail on it

#### Scenario: Change after the trailer
- **WHEN** a later commit changes another file `init.md` claims
- **THEN** the `co-change` warning on `init.md` is still reported

### Requirement: An acknowledgement needs a reason and a target
ID: acknowledgement-needs-reason
Provenance: code

A trailer without a reason, naming no doc, or naming a doc `co-change` does not warn on
SHALL acknowledge nothing and SHALL be reported as an info finding.

#### Scenario: Missing reason
- **WHEN** a commit in the range carries `Irminsul-Reviewed: co-change docs/components/init.md` with no reason
- **THEN** the `co-change` warning on `init.md` is still reported, and the trailer is reported as lacking a reason

#### Scenario: Unused trailer
- **WHEN** a trailer names a doc whose claimed sources did not change in the range
- **THEN** the trailer is reported as unused

### Requirement: A matching pin suppresses evidence drift
ID: pin-suppresses-drift
Provenance: code

When a claim records a pin for an evidence file and the file's current normalized hash
equals it, `evidence-drift` SHALL NOT report that file; when they differ, the file SHALL
be judged by the commit-time comparison, as one without a pin is.

#### Scenario: Evidence unchanged since the pin
- **WHEN** a claim's evidence file was committed after the doc, and its normalized hash equals the claim's pin
- **THEN** no `evidence-drift` is reported for that claim

#### Scenario: Evidence changed since the pin
- **WHEN** the evidence file's normalized hash differs from the pin, and it was committed after the doc
- **THEN** `evidence-drift` is reported naming that evidence file

#### Scenario: Doc updated beside the evidence
- **WHEN** the evidence file's normalized hash differs from the pin, and the doc was committed after it
- **THEN** no `evidence-drift` is reported for that claim

### Requirement: Re-pin writes claim pins
ID: re-pin-writes-claim-pins
Provenance: code

`irminsul anchors --re-pin --doc <doc>` SHALL write the current normalized hash of every
evidence file of every claim in that doc, and SHALL drop a pin on a path the claim no
longer cites.

#### Scenario: Re-pin after review
- **WHEN** `irminsul anchors --re-pin --doc docs/foundation/enforcement.md` runs
- **THEN** every claim in that doc records a pin for each evidence file, and a following `irminsul check` reports no `evidence-drift` for them

#### Scenario: Pin left on a path the claim no longer cites
- **WHEN** a claim's `pinned` names a path that is not in its `evidence`, and `irminsul anchors --re-pin --doc <doc>` runs
- **THEN** the doc still parses, the command exits 0, and the pin on that path is removed

## Tasks

- `T1` Read `Irminsul-Reviewed` trailers for the commits in a diff range. (req: trailer-acknowledges-co-change)
- `T2` Suppress acknowledged `co-change` warnings and report them as info. (req: trailer-acknowledges-co-change)
- `T3` Report trailers that lack a reason, name no doc, or acknowledge nothing. (req: acknowledgement-needs-reason)
- `T4` Add the optional `pinned` map to the claim schema. (req: pin-suppresses-drift)
- `T5` Skip pinned evidence whose normalized hash still matches in `evidence-drift`. (req: pin-suppresses-drift)
- `T6` Write claim pins from `anchors --re-pin`. (req: re-pin-writes-claim-pins)

## Resolution

Accepted as revised after review: a trailer covers only the changes before its commit and
reports as info when it acknowledges nothing, and a pin only suppresses drift. Recorded in
[A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md).
