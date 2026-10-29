---
id: every-warning-hint-has-an-answer
title: "Each finding code has one answer"
status: stable
describes: []
rfc_state: accepted
affects:
  - change
  - checks
  - cli
  - config
  - context
  - docgraph
  - frontmatter
  - init
  - new-list-regen
resolved_by: docs/decisions/finding-classes-decide-what-blocks.md
summary: Every finding code declares one answer, a commit trailer is the one acknowledgement step, and the dead ends an audit of all 174 codes found get an answer here or in a separate bug fix, so the gate that fails on hints never fails a correct doc; an accepted RFC's tasks also gain checkboxes, and ticking the last one asks for finalization.
required_updates: []
weight: large
---

# Each finding code has one answer

## Summary

A correct doc can always reach a green run of this repository's gate, which fails on hints.
Every finding code declares one answer, a commit trailer becomes the one acknowledgement step,
and the routes around an answer close. Of 24 codes an audit of all 174 found trapping a correct
tree or adding noise, this answers or deletes 15, bug fixes correct 6, five of them already on
main, a decision record retired 2, and one duplicate stays. An [RFC](../GLOSSARY.md#rfc)'s tasks
also gain checkboxes, and ticking the last asks for finalization. Thirteen decisions, all
answered.

## Problem

A **hint** is a finding that needs judgement; a **certain** finding proves a rule is broken.
Failing the gate on hints is fair only if each hint has an **answer**, an honest way for a
correct doc to turn green.

A typo fix in an accepted decision record gets a `decision-rewritten` warning. Nothing honest
clears it, and an ignore comment cannot reach it, because it has no line. The answers that do
exist overlap: re-pinning one paragraph also clears a warning about the whole doc.

## How it works

**Every code declares one of four answers**, which `irminsul explain` prints: **fix**, the doc
or config is wrong; **line**, an ignore comment on its line; **pin**, a re-pin until the code
moves; and a **trailer** in a commit message, the sign-off for one change. A test fails on a
code with none.

**One step reads trailers**, matching each finding's code, path and subject, and prints what
it accepts at info with the reason. **Each code takes only its own answer**: an ignore comment
waives only a line code, and a re-pin no longer counts as editing a doc.

**Dead ends get an answer.** A trailer answers folding an implemented RFC into a decision
record or removing an anchor whose code remains; a broken base config is compared through the
last one that loaded; two certain codes that judge meaning become hints; four warnings with
no line get one answer each.

**Noise goes**: the `mtime-drift` check and the cached-link notice. **Drafts stop failing the
hint gate.** Adopters keep failing on certain findings alone. Not chosen: any new waiver.

**A task list says when an RFC is done.** Each task gets a checkbox, ticked in the pull request
that implements it. Say an accepted RFC has three tasks: one pull request implements T1 and T2
and ticks both, so `change status` reads "2 of 3 tasks done"; the next ticks T3, so the gate
fails until that pull request runs `change finalize`, once the owner agrees.

## Cost and risk

A declaration per code, a test, a guard, and one step replacing nine record tests. Raising a
link-cache setting becomes certain, failing an adopter's default gate without a trailer. A
trailer lapses when a later commit touches the file it is about, and re-reading an anchored
doc takes a re-pin and a trailer. `co-change` reading the code repository's range keeps the
drift signal `mtime-drift` gave, at the price of passing that range in.

A tick is the agent's statement, and Irminsul, which reads only the repository and git, cannot
check it: review, finalize's mechanical gates and the owner's go-ahead do. An RFC that is never
ticked shows in `change status` but is not forced to finalize.

## Decisions

All answered by the owner on 2026-10-28, except 1 and 7 revised, 10 settled and 11 to 13 added
on 2026-10-29. Each one's reasons are under Decisions in full.

1. **A change's sign-off is a commit trailer only.**
2. **A setting with a known direction is sealed.**
3. **Each code takes one answer.**
4. **Every code declares an answer, info included, with no new waiver.**
5. **Draft leniency lives in one place.**
6. **A trailer answers removing an implemented RFC**; editing one stays sealed.
7. **`mtime-drift` is deleted**, and `co-change` reads the code repository's range.
8. **A trailer answers removing an anchor or inventory entry.**
9. **A broken base config is compared through the newest earlier one that loads.**
10. **The inventory `foreign` list is deleted.**
11. **The RFC-scope comparison leaves `check --diff`**, done on main.
12. **Ticking the last task is what forces `change finalize`.**
13. **A reminder, not a finding, lists an RFC's open tasks.**

## Design detail

### Decisions in full

All answered by the owner on 2026-10-28, except 1 and 7 revised, 10 settled and 11 to 13 added
on 2026-10-29.

1. **A change's sign-off is a commit trailer only**, so there are four answers; a decision
   record answers no finding.
2. **A setting with a known direction is sealed**, so only loosening it needs a trailer.
3. **Each code takes one answer**, closing four routes around it.
4. **Every code declares an answer, info included, with no new waiver.**
5. **Draft leniency lives in one place**, not four.
6. **A trailer naming an implemented RFC's path answers its removal**; edits stay sealed, and a
   moved pin is no edit.
7. **`mtime-drift` is deleted and `co-change` reads the code repository's range**: as a time
   finding the check would still fail the local gate, and the extension keeps its
   cross-repository signal.
8. **A trailer answers removing an anchor or inventory entry**, as it does for a claim.
9. **A broken base config is compared through the newest earlier one that loads**, else
   reported at info: a change cannot alter its own base.
10. **The inventory `foreign` list is deleted**: an ignore comment on the flag's line answers
    the same error, and the list also hid a wrong flag of our own program.
11. **The RFC-scope comparison leaves `check --diff`**, and a separate decision record retires
    its two findings. Done on main on 2026-10-29; that record was folded into
    [RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)
    at the second history reset.
12. **Ticking the last task is what forces `change finalize`**; a tick is the agent's
    statement, not Irminsul's.
13. **A reminder, not a finding, lists an RFC's open tasks** when a change touches its
    component, and never fails a run.

### The decisions this builds on

- [CI runs each gate once, and the Action takes typed inputs](../decisions/ci-runs-each-gate-once-and-the-action-takes-typed-inputs.md)
  made this repository's CI fail on hints, because a gate "that passes on a hint contradicts
  the rule this repository ships, that a hint needs an answer," so a hint a reviewer should
  answer cannot merge unanswered. It names
  `.github/workflows/ci.yml`, which runs `irminsul check --diff "origin/<base>" --fail-on hint`
  on a pull request and `irminsul check --fail-on hint` on a push to `main`. Time findings are
  left out of a run given a diff range and fail nothing on `main`. This proposal leaves the
  workflow as it is and makes that gate fair: once every code has an answer, a correct doc
  always has a way to green.
- [Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)
  still rejects blocking new hints because "a hint on a correct doc has no honest fix." Both
  decisions hold only if every hint has an answer. It also decides that a demoted draft
  finding is a warning that `--fail-on hint` fails on, which this proposal qualifies (see
  Drafts).
- [A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md)
  answered two hints that carry no line: `co-change` with a trailer and
  `claim-provenance/evidence-drift` with a pin.
- [A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md)
  compares every field of `irminsul.toml` with the merge base, the sealed-settings decision,
  and lets a new decision record naming a setting clear a hint about it. This proposal
  replaces that excuse with a trailer through the acknowledgement step and qualifies its
  treatment of a base config that does not load (decision 9).
- [RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)
  makes removing an implemented RFC certain, and its Consequences say a consolidation "is
  merged past the failing seals". Decision 6 gives consolidation an answer instead.
- [Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)
  decides that "a removed anchor or inventory entry has no excuse". Decision 8 qualifies it.
- [Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)
  describes `foreign` as naming other tools' identities. Decision 10 qualifies it.
- This proposal builds on the single check runner that the cleanup of word-list checks and
  duplicate passes left, and on an audit of every finding code on main at commit 4110346:
  174 codes, each read for whether a correct tree can raise it and what clears it.

### What has no honest answer today

Each of these fails this repository's gate today, or clears a finding without the answer it
needs. The audit reproduced each one marked as such in a scratch clone; the two narrowings
were found by reading the code.

- A change refactors a source file whose doc is more than 30 days old. It gets both
  `co-change`, which a trailer answers, and `mtime-drift/drift-detected`, which only an edit to
  the doc clears; the check's own explanation calls that edit clearing the signal without
  answering it.
- A change lowers `checks.external_links.ttl_hours` from 168 to 24, so the link check asks
  more. No seal gives that field a direction, so `diff-integrity/unreviewed-setting-change`
  asks for a new stable decision record naming it.
- A change raises the same field and adds such a record. The record stops the finding from
  being created, so the run shows nothing, while a finding a trailer answers prints at info
  with its reason.
- A commit changes an anchored function, and its doc is re-pinned. That clears
  `claim-anchor/pinned-drift`, and since `co-change` counts any doc edit that is not whitespace
  (`whitespace_only_docs`), it also clears the co-change warning about the whole doc.
- An ignore comment naming `claim-anchor/pinned-drift` on an anchor's line hides every later
  drift of that anchor.
- Adding an identity to an inventory entry's `foreign` list clears the certain
  `inventory-drift/unknown-mention`, and nothing reports it: `_inventory_weakening` compares
  `explained_in`, `complete` and `omit` only.
- A claim moved from `review-on-divergence` to `follows-evidence` is not reported, and once
  that is the base, removing the claim is not reported either: `_removed_governance` reads the
  relation at the base and skips `follows-evidence`, and only `governs-evidence` is protected,
  by `_rewritten_governing_claims`.
- Folding an implemented RFC into a decision record, and deleting it, is
  `diff-integrity/implemented-rfc-removed`, certain, and a record naming its path does nothing
  (reproduced). Re-pinning an anchor inside it is `implemented-rfc-changed`, certain.
- Pruning a paragraph with its anchor on code that still exists is
  `diff-integrity/anchor-removed`, and dropping an inventory entry whose source still matches
  files is `inventory-removed`; both are certain, and no record excuses either (reproduced).
- The pull request that repairs a base `irminsul.toml` that does not load gets
  `diff-integrity/base-config-unreadable`, and with an adoption record also the certain
  `adoption-base-unreadable` (reproduced). No change can repair its own base.
- Fixing a typo in an accepted decision's `## Decision` is `decision-rewritten`, which nothing
  clears (reproduced). Splitting a doc, linking both halves and removing the old prose still
  leaves `owner-changed` (reproduced). `rfc-follow-through/stable-doc-links-draft-rfc` and
  `import-deps/hallucinated-dependency` carry no line.
- A bare git flag such as `--no-verify` in a code span is the certain
  `inventory-drift/unknown-mention`, and a python fence showing a user's own Pydantic model is
  the certain `schema-leak/pattern-match` (reproduced). An ignore comment cannot cover a fenced
  line anyway: `_scan` skips every line its `FenceTracker` consumes.
- A run of the audit's branch printed 41 `glossary-discipline/unlinked-term` lines at info,
  and a run of main on 2026-10-29 prints 47. Of the 41, 35 had a fix. The other 6 cannot be fixed, because the detector reads the body through
  `_masked_body`, which masks code and comments, while the fixer reads it through
  `_masked_for_link`, which also masks headings and links. The 6 use a term only as a link's
  text (`docs/components/anchors.md`, `docs/components/init.md`,
  `docs/foundation/enforcement.md`, `docs/components/orient.md`, `docs/components/refs.md`) or
  only in a heading (`docs/rfcs/INDEX.md`). On main the audit counted 44 and 11.
- A fresh `irminsul new rfc` plus `irminsul new adr` gives 10 draft-demoted warnings on main
  on 2026-10-29, 8 on the RFC and 2 on the record, and `--fail-on hint` fails on them.

### Declarations

- Beside `classes`, each check declares `answers`: for every hint or time code it explains,
  info included, one of `line`, `trailer`, `pin` or `fix`, with the sentence a reader acts
  on. A certain code declares `trailer` when a trailer answers it, and nothing otherwise,
  which means `fix`. `irminsul explain` prints the answer, and a finding's suggestion names
  it, so a suggestion that sends the reader to another finding goes, such as
  `history-depth/no-history` offering to disable checks. The table below writes the
  acknowledgement as acknowledge (trailer); a check declares it as `trailer`.
- Each answer lasts as long as what its finding reports. A **line** sits on the line it is
  about, in a doc or a guidance file, and an ignore comment waives it as long as the mismatch.
  A **trailer**, `Irminsul-Reviewed`, acknowledges a finding about one change, as it already
  does for `co-change`. A **pin** re-pins drifted content, as it already does for
  `evidence-drift`, and lasts until the content moves. A **fix** is honest because the doc or
  config is wrong whenever the finding fires.
- A trailer's excuse applies in the change that carries it: once that change merges, the
  comparison it answered no longer runs, and only the reason lasts, in git history. A decision
  record still holds what a later reader should find, such as a setting or a gate file's
  rationale, but it answers no finding.
- Time codes declare answers too, and none is a trailer, since a run given a diff range
  leaves them out.
- The declaration test is static, over every check, registered or not. It fails on a hint or
  time code with no answer, on an answer for a code the check does not explain, and on a
  certain code declared anything but `trailer`, so a new code is held to this the day it is
  written, whether or not any test produces it.
- The runtime guard verifies what the static test cannot. It wraps `run_checks`, the one runner
  every surface calls, so findings from the CLI, `context --after-edit` and the MCP server all
  pass through it. It fails a test in which a code declared `line` is reported without a line
  in a file the ignore-comment pass reads, a fenced line included once the pass covers fences,
  or a code declared `trailer` is reported without a subject.

### The acknowledgement step

One step in the shared runner, after every check and after classes are applied, accepts
findings for one change. Its one source is the `Irminsul-Reviewed` trailers of the change's
commits.

- **Every finding it can accept carries a subject**: a setting's dotted name, a claim id, an
  anchor, an inventory entry, or the file itself when the finding is about a whole file.
- **It matches code, path and subject, through the answer the code declares.** A trailer
  states all three: `Irminsul-Reviewed: <code> <path> [<subject>] reason="..."`. A check with
  one code may be named by check; a check with several must be named by code, so a trailer for
  one excluded source path cannot also cover a removed test root in the same file. For a
  setting the path is `irminsul.toml` and the subject the dotted name. A trailer accepts only
  a code declared `trailer`; one that names any other code accepts nothing.
- **It keeps the finding's own code.** An accepted finding is reported at info under its own
  code, quoting the trailer's reason. `co-change/acknowledged` goes, and
  so do `co-change/invalid-acknowledgement` and `co-change/unused-acknowledgement`: a trailer
  that names a code not declared `trailer`, or does not parse, is `acknowledgement/invalid`, and
  one that matches no finding is `acknowledgement/unused`, both at info, because a commit
  trailer cannot be removed without rewriting history.
- **A trailer covers what came before it.** It stops covering a finding once a later commit of
  this change, or uncommitted work, touches a file the finding is about. A merge and the base's
  own history do not count.
- **No check tests for a decision record.** `diff-integrity` does so in nine places today, each
  looking for the subject in a code span of the `## Decision` sections the change adds. Under
  this proposal each of these findings is always created, with its subject, and the step
  accepts it through a trailer:

| Where in `diff_integrity.py` | Codes | Subject |
|---|---|---|
| `run_diff_integrity` | `baseline-grew` | the baseline path |
| `run_diff_integrity`, passed to `_adoption_seal` | `adoption-record-removed` | the adoption record path |
| `_removed_governance` | `claim-reworded` | the claim id |
| `_removed_governance` | `claim-removed`, `governing-claim-removed` | the claim id |
| `_removed_governance` | `inventory-weakened` | the doc path |
| `_changed_gate_files` | `gate-file-changed` | the gate file's path |
| `_rewritten_governing_claims` | `governing-claim-changed` | the claim id |
| `_config_weakening`, unsealed field | `unreviewed-setting-change` | the dotted name |
| `_config_weakening`, sealed field | `check-disabled`, `layer-rule-disabled`, `setting-weakened`, `source-excluded`, `extra-doc-removed`, `rules-narrowed` | the dotted name, or the check name for `checks.enabled` |

`baseline-grew` keeps its second excuse, the change that adopts Irminsul, which is not a
trailer. Five codes take a trailer for the first time, each with its own subject:
`implemented-rfc-removed` (the RFC's path at the base), `anchor-removed` (the anchor as
`path#symbol`), `inventory-removed` (the entry as `source#kind`), and the new
`files-dropped` and `claim-downgraded` (the dotted name and the claim id).

For example, a pull request has three commits. Commit 1 raises
`checks.external_links.ttl_hours` from 168 to 720 and carries
`Irminsul-Reviewed: diff-integrity/setting-weakened irminsul.toml checks.external_links.ttl_hours reason="slower links are fine here"`.
Commit 2 fixes a typo in `src/irminsul/checks/external_links.py` and carries
`Irminsul-Reviewed: co-change docs/components/checks.md reason="typo"`. Commit 3 edits the same
file again. Today a stable record naming the setting would stop the finding from being created,
so the run prints nothing about it, and the co-change warning returns because commit 3 came
after the trailer. After, the setting is `setting-weakened`, printed at info with commit 1's
reason, and the co-change warning returns exactly as before. Both go through the same step. A
later pull request that lowers the setting to 24 reports nothing and needs no trailer.

### Setting directions

`_SEALS` gives a direction to every field of the schema except seven, and to none of the four
fields compared inside a surface rule kept on both sides. Four of the seven get one, each
reported as `setting-weakened` when it moves that way and as nothing when it moves the other:

| Setting | Weaker when |
|---|---|
| `checks.schema_leak.protected_paths` | `none-means-all`: unset means every doc in the components layer, so setting the list, or dropping an entry, narrows it |
| `checks.external_links.ttl_hours` | `raised`: a cached result is trusted longer |
| `checks.external_links.timeout_seconds` | `raised`: a slow link has longer before it counts as unreachable |
| `checks.external_links.cache_path` | `any-change`: it could point at a committed cache |

These have no clear direction yet, so `unreviewed-setting-change` stays for them and for any
field the schema gains later, and a trailer answers it:

- `frameworks.command_names`: empty means the names come from `[project.scripts]`.
- `paths.baseline` and `paths.adoption`: the baseline ratchet and the adoption seal already
  compare the file at the base's path with the one at the change's.
- `surface.rules.pattern`, `surface.rules.identity`, `surface.rules.guard` and
  `surface.rules.mention_pattern`, compared for each rule kept on both sides: a regular
  expression has no direction.

The seal on `overrides.mtime_drift_days` goes with the check it tunes.

### One answer per code

- **An ignore comment waives only a code declared `line`.** The filter already refuses a
  certain code, as `ignore-comment/certain-finding`. It now also refuses a hint or time code
  declared anything else, as `ignore-comment/wrong-answer`, certain like the other misuse
  codes, whose suggestion names the answer the code declares. A comment naming a whole check
  applies code by code, so it waives that check's `line` codes and is `ignore-comment/unused`
  if it waived nothing.
- **A doc change that only moves pins does not update that doc for `co-change`.** Today
  `co-change` sets aside a whitespace-only doc change and nothing else. A pin, the hash on an
  anchor in the body or a claim's `pinned:` entry in frontmatter, is written by
  `anchors --re-pin` to record which version of the code was re-read, and `_decision_wording`
  already leaves anchor pins out when it judges whether a decision was rewritten. One reading
  with pins left out serves `co-change`, `decision-rewritten` and `implemented-rfc-changed`,
  so moving a pin rewrites nothing for any of them. A re-read of an anchored doc then takes the
  re-pin for the drift and a trailer, or a real edit, for `co-change`.

### A claim downgrade, sealed

A claim whose relation at the base is `review-on-divergence`, stated or omitted, and is
`follows-evidence` in the change is `diff-integrity/claim-downgraded`, a hint declared
`trailer`, answered by a trailer naming the claim id. The relation is read from the base, as
the governing-claim rules read it, so a later change that removes a claim already
`follows-evidence` stays unreported: the downgrade was the decision.

With `foreign` deleted (decision 10), no seal guards its additions.

### Sealed records and removed governance

- **Folding an implemented RFC.** `implemented-rfc-removed` is declared `trailer`, its subject
  the RFC's path at the base. A trailer naming that path accepts it, and its reason points at
  the decision record that absorbs the RFC. Editing stays sealed: `implemented-rfc-changed` is
  still a fix, restore the record or propose a new RFC, but it compares the two texts through
  the pin-blind reading above, so a re-pin inside an implemented RFC is no change.
- **That gives the other sealed dead ends an exit.** An implemented RFC whose component doc was
  deleted (`change-binding/unknown-component`), whose required-update doc was deleted
  (`missing-required-update-path`), or whose link to a renamed glossary heading broke, cannot
  be edited; it is folded into a decision record instead, and a trailer answers the removal.
- **Pruning true governance.** `anchor-removed` is declared `trailer`, its subject the anchor
  as `path#symbol`, such as `src/irminsul/checks/base.py#CheckFlag.opt_in`. `inventory-removed`
  is declared `trailer`, its subject the entry as `source#kind`, such as
  `src/irminsul/cli.py#cli-options`: the removal seal already identifies an entry by kind and
  source, and `docs/components/cli.md` holds two entries on that one source. The finding
  prints the subject to cite. Each answers pruning a declaration whose code is still there, as
  a trailer naming a claim id answers `claim-removed`. The audit's later option, staying silent
  when an anchor goes with its paragraph, is not part of this.
- Accepting this proposal qualifies
  [RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)
  and [Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)
  accordingly, each in place.

### A base config that does not load

Since the cleanup, the base config is read as the base wrote it, dropping keys this version no
longer has and keeping check, pack and language names it no longer registers, so removing a
check is reported as `check-disabled` rather than as an unreadable base. What remains is a
base config that is not valid TOML, or holds a value the schema rejects.

- **One loader serves both readers of the base config**, the config seal and the adoption
  seal. When the `irminsul.toml` at the base does not load, it walks back through the commits
  that changed `irminsul.toml` before the base and uses the newest version that loads, at one
  read per version. A setting the repairing change loosens is then still compared, against the
  config from before it broke.
- **Only when no earlier version loads** is `diff-integrity/base-config-unreadable` reported,
  a hint at info declared `fix`: the change that repairs the config ends it once it merges.
  `adoption-base-unreadable` goes, merged into it.
- The earlier draft made this certain, with a sign-off to answer it. Rejected by decision 9: a
  change cannot alter its own base, so the pull request that repairs the config would always
  need a sign-off for doing the repair.
- This qualifies [A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md),
  whose decision reports a base config that does not load as a hint and judges sealed folders
  by the change's own config, and accepting this proposal says so in that record.

### Deleting `mtime-drift`

- **What goes.** The check leaves the registry and this repository's `checks.enabled`, with both
  its codes, the setting `overrides.mtime_drift_days` and the `[overrides]` table it is alone
  in. `history-depth` stops naming it without an edit, since it reads `CheckFlag.reads_history`.
  A config that still enables the check fails to load, as any unregistered name does, and one
  that still sets the setting is refused with a message that says the check is gone, as
  `checks.hard` is today.
- **Why.** A doc whose source changed is asked about by `co-change` in the change that edits the
  source, by a pin when its paragraph is anchored or its claim's evidence is pinned, and by
  `list review --changed`. `mtime-drift` asked again, 30 days later, with an edit to the doc as
  its only answer.
- **The tombstone.** In the change that deletes the check,
  [Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)
  declares under `retires:` an entry with `id: mtime-drift`, `kind: concept`, the check's name and setting as `matches`,
  and guidance naming `co-change`, pins and `list review --changed`. `retired-references` then
  reports current guidance that still presents the check as live. Every live mention is
  reworded or links the record: `docs/components/` (anchors, baseline, checks, config,
  docgraph, git), `docs/guides/private-docs.md`, the README, the decisions index's and the
  decision-record template's example of a setting change, the comments in the scaffolded config and
  workflows, and the Alternatives of
  [A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md).
- **The foundation.** `docs/foundation/principles.md` names mtime drift as one of three
  why-freshness mechanisms. The principle holds through anchored claims and the review queue;
  only those two words go, and the implementing change reports the edit to the foundation.
- **Adopters.** The CHANGELOG tells an upgrader to delete the name and the setting; that
  change's own `--diff` gate reports `check-disabled`, which a trailer naming `mtime-drift`
  answers.
- **`co-change` reads the code repository's range.** In the siblings layout the code lives in
  another repository, whose pull request passes its range as `--source-diff`; today that range
  reaches only `diff-integrity/adoption-debt-touched`, through `ChangeRange.source_changed`.
  `co-change` also reads it, so a source file that range changed and that a docs-repository
  doc claims asks that doc to be re-read, as in the same-repository layout. The doc cannot be
  edited in the code repository's pull request, so a trailer on a commit of that range
  answers the finding, under the lapse rule above. This closes the drift gap deleting
  `mtime-drift` would otherwise open, and the words in the private-docs guide and the
  scaffolded nightly workflow that name `mtime-drift` as the cross-repository signal are
  reworded to name `co-change`.

### RFC scope is judged by the change commands

The comparison of an RFC's `affects` with the components a change touches lives only in
`change verify` and `change finalize`, whose `unreconciled-scope` gate stays as it is. A
separate change left it out of `check --diff` on 2026-10-29 and retired
`change-binding/touched-but-undeclared` and `change-binding/declared-but-untouched`; the record
that decided it was folded into
[RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)
at the second history reset, with its tombstone. This proposal neither narrows nor answers
either code, and its table lists both as retired.

### Task checkboxes and finalization

A task item may open with a checkbox: `` - [ ] `T1` text (req: id) `` is open and
`` - [x] `T1` text (req: id) `` is done. `_parse_task_bullet` in
`src/irminsul/docgraph_index.py` reads the box before the id, and `Task` gains a `done` field
that is empty when there is no box. The id, text and reference rules are unchanged, so a box on
an item with no id is still `requirement-grammar/task-missing-id`.

- **Counting.** A task with no box is valid and counts as open, so implemented RFCs and drafts
  written before checkboxes parse as they do today. An RFC none of whose tasks has a box is not
  tracked: `change status` says so rather than "0 of 7 tasks done", which would read as
  unstarted, and the finding below is never raised for it.
- **The finding.** `rfc-follow-through/all-tasks-done` is certain and declared `fix`. The
  `RfcFollowThroughCheck` reports it on an accepted RFC with at least one task, every task
  ticked and no task item that fails to parse, which has findings of its own. Its message is
  "every task is done: run `irminsul change finalize`". A draft or an implemented RFC is never
  asked.
- **Finalization is not blocked by it.** The rule is one predicate in
  `src/irminsul/change/gate.py`, as the other rules `gate` shares with a check are, and `gate`
  judges it without raising it, as it does `update-missing-implements`. A finalization or a
  `change status` blocked by the finding that asks for it would leave no way to clear it.
- **Progress.** `TaskItem` and `TaskSummary` in `src/irminsul/change/report.py` carry the done
  state, and `_task_summary` prints "4 of 7 tasks done" before the evidence counts. The count
  comes from the RFC alone, so it shows even when no diff baseline resolves.
- **The reminder.** For each accepted RFC with an open task whose `affects` names a component
  in the change's own footprint, from `touched_components` as `change verify` computes it,
  `list review --changed` and `context --after-edit` print the RFC and its open tasks, worded
  "if this is its work, tick the task". The first adds a marker to `MARKER_MEANINGS` in
  `src/irminsul/listing/review.py`; the second adds a block beside the claim reviews in
  `src/irminsul/context.py`. It is not a `Finding`: it has no code, class or answer,
  `irminsul check` never reports it, and it exists only while the pull request that touches the
  component is open, because it is read from that diff. A wrong one is read and left.
- **Where it is written down.** The scaffold `src/irminsul/new/templates/rfc.md.j2` shows the
  box, and step 4 of `docs/guides/agent-protocol.md` says the agent ticks a task in the pull
  request that implements it, and finalizes once the owner agrees. `docs/components/change.md`
  says tasks carry "never assignees, deadlines or status"; the checkbox becomes the one status
  a task carries, and accepting this proposal qualifies that sentence in the record that
  governs the change lifecycle.
  Completion is not mechanically knowable, so it is authored, not derived.
- **The recorded limitation.** A tick is the agent's statement. Irminsul reads only the
  repository and git, so it cannot see whether a task's code exists, whether the tick is in the
  same pull request as that code, or whether it is true, and a pull request description, where
  an agent might say so, is out of its reach. Review, finalize's mechanical gates and the
  owner's go-ahead check a tick. An RFC that is never ticked shows in `change status` but
  nothing forces it.

### The warnings that carry no line

- **`decision-rewritten`** is declared `trailer`, its subject the record's path, for a wording
  correction such as a typo. A changed decision still needs a superseding record; the reviewer
  reads which of the two the trailer claims.
- **`owner-changed`** is reported only while the old owner's body still names the moved file,
  through the sentence reader `list review --changed` already uses, `_moved_file_sentences`, so
  the rule has one implementation. It is reported on the old doc, its subject the moved file,
  quoting the first sentence that names it, and declared `trailer`: a mention re-read and found
  right is acknowledged, and a stale one is edited away, which clears it. The earlier draft's
  route, a link between the two docs, goes: a link says nothing about the old prose.
- **`stable-doc-links-draft-rfc`** carries the line of the link to the draft RFC and is
  declared `line`. An ignore comment there answers it while the RFC is a draft and becomes
  `ignore-comment/unused` once it is not, which asks for the comment's removal.
- **`import-deps/hallucinated-dependency`** stays a warning declared `fix`. `imported_paths`,
  which `new-dependency` shares, also reads a call of `importlib.import_module` whose argument
  is a string literal. An entry that no import backs, such as a dependency through a
  subprocess or a registry, moves out of `depends_on` into a sentence of the body that links
  the doc and says how the dependency works, which `refs` lists as a weak reference.
- **`base-config-unreadable`** is the section above.

### Two certain codes that judge meaning

- **An ignore comment covers a fenced block.** A comment written inside a fence is part of the
  example and is still never read. A standalone comment directly above a fence covers every
  line of that fenced block, and an `ignore-start` and `ignore-end` pair covers the fenced
  lines between them. This comes first, shown by a planted test, since most of the findings
  below sit inside fences.
- **`inventory-drift/unknown-mention` splits by what the span is.** A span that invokes this
  project's program names a flag of our own program, and stays certain under its code. A span
  that is a bare flag, with no program before it, may be git's or any tool's, and is reported
  as `inventory-drift/unattributed-mention`, a hint declared `line`.
- **`schema-leak/pattern-match`** becomes a hint declared `line`: a python fence showing what a
  user writes is a correct doc, and only a reader can tell it from a leaked type definition.
- **Deleting `foreign`** (decision 10). The field joins `frontmatter/retired-field`,
  whose suggestion names an ignore comment on the line, and its readers in
  `listing/command.py` and `listing/review.py` go. This repository's stale list in
  `docs/components/cli.md` is removed in the same change.

### Drafts

A certain finding on a draft doc that the draft exemption demotes is reported as a warning, so
`--fail-on hint` fails on it, as
[Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)
decides. Since CI fails on hints, a draft RFC on the main branch with an unfinished requirement
turns the build red. A draft is unfinished on purpose, and an RFC in flight on the main branch
is a normal state. So failing on hints does not fail on a finding the draft exemption demoted.
It still fails the moment the doc becomes stable. The decision record that accepts this
proposal qualifies that record accordingly.

Draft leniency is built four times today, and moves to one place:

- `drafts_exempt`, which each check declares and the pipeline applies, stays the one place.
- `certain_severity` is called in eight checks to pick a warning for a draft, and
  `apply_classes` always overwrites the severity it picks, so it is dead code. The audit's
  reproductions show it: a draft orphan doc, a duplicate section in a draft decision record and an unknown
  component on a draft RFC are each still an error. A planted test comes first, then the
  function goes.
- `phantom-layer` reports `layer-under-construction` at info instead of `hollow-layer` for a
  draft INDEX. `hollow-layer` joins `drafts_exempt` instead, and `layer-under-construction`
  goes. A draft INDEX with no content docs then gets a demoted `hollow-layer`, which the rule
  above keeps from failing the hint gate.
- `code-references` skips its hints on a draft inside its own run. That skip becomes a
  declaration the pipeline applies beside `drafts_exempt`.

### The cached-link notice

`external-links/cached-results` is an info finding on every run that reads a cached result, and
the only way to stop it is to delete a valid cache. Its count and its oldest observation move
into the run's summary: a notice that nothing answers is not a finding.

### Answers for every code

One row per code: the 174 the audit read, the four that `rfc-structure` added on main after
it, and the seven this proposal adds, ten of them retired, two already on main by the RFC-scope
decision. A **bold** note marks a change this proposal makes. Three allowances stand beside the answers and are not answers: the **draft
allowance** demotes a drafts-exempt code on a draft doc, the **adoption-record allowance**
covers files unowned on the day of adoption, and the **baseline** covers any certain code of a
registered check other than a suppression audit, so it is not repeated per row.

Coverage: fix 138, acknowledge (trailer) 23, line 11, pin 3, retired 10.

| Code | Class | Answer | Note |
|---|---|---|---|
| `frontmatter/parse-error` | certain | fix |  |
| `frontmatter/missing-frontmatter` | certain | fix |  |
| `frontmatter/id-mismatch` | certain | fix |  |
| `frontmatter/duplicate-id` | certain | fix |  |
| `frontmatter/misspelled-field` | certain | fix |  |
| `frontmatter/retired-field` | certain | fix | gains `inventory.foreign` |
| `frontmatter/missing-summary` | certain | fix | draft allowance |
| `globs/missing-source-root` | hint | fix | the configuration is wrong |
| `globs/broken-symlink` | certain | fix |  |
| `globs/source-root-escape` | certain | fix |  |
| `globs/empty-describes-pattern` | certain | fix |  |
| `globs/ambiguous-source-display` | hint | fix | the configuration is wrong |
| `uniqueness/duplicate-claim` | certain | fix |  |
| `uniqueness/undocumented-file` | certain | fix | adoption-record allowance |
| `uniqueness/unlinked-overlap` | hint | fix | until `a-source-file-has-one-claim` retires it |
| `links/broken-link` | certain | fix |  |
| `links/unknown-anchor` | certain | fix | GitHub's slugger, fixed on main |
| `schema-leak/pattern-match` | hint | line | **changed** from certain; needs the fenced-line scan |
| `coverage/missing-tests-entry` | certain | fix | draft allowance |
| `coverage/tests-path-missing` | certain | fix |  |
| `prose-file-reference/unlinked-reference` | certain | fix |  |
| `agents-manifest/manifest-missing` | certain | fix | `irminsul fix` writes it |
| `agents-manifest/manifest-unreadable` | certain | fix |  |
| `agents-manifest/missing-generated-markers` | certain | fix |  |
| `agents-manifest/generated-section-drift` | certain | fix | `irminsul fix` writes it |
| `agents-manifest/missing-required-heading` | certain | fix |  |
| `rfc-lifecycle/missing-rfc-state` | certain | fix |  |
| `rfc-lifecycle/dangling-resolved-by` | certain | fix |  |
| `rfc-lifecycle/broken-implements` | certain | fix |  |
| `rfc-lifecycle/implements-before-implemented` | certain | fix |  |
| `rfc-lifecycle/implemented-without-evidence` | certain | fix |  |
| `retired-references/inactive-retirement` | certain | fix |  |
| `retired-references/retirement-still-live` | certain | fix |  |
| `retired-references/ambiguous-retirement` | certain | fix |  |
| `retired-references/retired-reference` | certain | fix | reword, or link the phrase to the record that retires it |
| `retired-references/unmatched-generated-marker` | certain | fix | duplicates an `agents-manifest` code (Left open) |
| `retired-references/guidance-unreadable` | certain | fix |  |
| `adr-structure/missing-section` | certain | fix | draft allowance |
| `adr-structure/duplicate-section` | certain | fix |  |
| `adr-structure/empty-decision` | certain | fix | draft allowance |
| `mtime-drift/no-git-history` | - | retired | the check is deleted |
| `mtime-drift/drift-detected` | - | retired | the check is deleted |
| `orphans/orphan-doc` | certain | fix |  |
| `stale-reaper/stale-deprecated-doc` | time | fix | delete it or set `removed` |
| `supersession/unknown-supersedes` | certain | fix |  |
| `supersession/status-not-deprecated` | certain | fix | accepts `removed`, fixed on main |
| `parent-child/wildcard-with-children` | hint | fix | until `a-source-file-has-one-claim` retires it |
| `parent-child/index-too-long` | hint | line | **gains a line**: the INDEX's first heading |
| `rfc-follow-through/status-not-stable` | certain | fix | `irminsul fix` writes it |
| `rfc-follow-through/missing-section` | certain | fix |  |
| `rfc-follow-through/adr-missing-rfc-link` | certain | fix |  |
| `rfc-follow-through/retained-questions` | certain | fix |  |
| `rfc-follow-through/stale-target-date` | time | fix | decide, reject, or move the date |
| `rfc-follow-through/accepted-not-implemented` | time | fix | implement, or reject (Left open) |
| `rfc-follow-through/no-required-updates-field` | certain | fix |  |
| `rfc-follow-through/missing-required-update-path` | certain | fix | skips `kind: create`, fixed on main; on an implemented RFC, fold it |
| `rfc-follow-through/update-missing-implements` | certain | fix | `irminsul fix` writes it |
| `rfc-follow-through/stale-claim` | certain | fix |  |
| `rfc-follow-through/stable-doc-links-draft-rfc` | hint | line | **gains a line**: the link's |
| `rfc-follow-through/all-tasks-done` | certain | fix | **new**: finalize the RFC; finalization is not blocked by it |
| `glossary-discipline/malformed-metadata` | certain | fix |  |
| `glossary-discipline/forbidden-synonym` | certain | fix |  |
| `glossary-discipline/unlinked-term` | hint (info) | fix | **changed**: the detector reads what the fixer links |
| `glossary-discipline/unused-term` | hint | line | above the term's heading in the glossary |
| `external-links/unreachable` | time | line |  |
| `external-links/cached-results` | - | retired | its count moves to the run summary |
| `boundary/missing-scope-limitations` | certain | fix | draft allowance |
| `boundary/unfilled-scope-section` | certain | fix | draft allowance |
| `phantom-layer/layer-under-construction` | - | retired | `hollow-layer` joins the draft allowance |
| `phantom-layer/hollow-layer` | certain | fix | draft allowance, **new**; counts sub-folders, fixed on main |
| `import-deps/hallucinated-dependency` | hint | fix | **changed**: reads literal `importlib` imports |
| `claim-provenance/evidence-not-repo-relative` | certain | fix |  |
| `claim-provenance/evidence-path-missing` | certain | fix |  |
| `claim-provenance/evidence-state-mismatch` | certain | fix |  |
| `claim-provenance/unknown-claim-ref` | certain | fix |  |
| `claim-provenance/evidence-drift` | hint | pin |  |
| `foundation-readiness/scaffold-placeholder` | certain | fix | draft allowance |
| `inventory-drift/no-extractor` | certain | fix |  |
| `inventory-drift/no-source-glob` | certain | fix |  |
| `inventory-drift/item-not-found` | certain | fix | `irminsul fix --confirm` removes it |
| `inventory-drift/undeclared-live-item` | certain | fix |  |
| `inventory-drift/stale-omit` | certain | fix |  |
| `inventory-drift/unexplained-live-item` | certain | fix |  |
| `inventory-drift/unknown-mention` | certain | fix | **narrowed** to a span that invokes this project's program |
| `inventory-drift/unattributed-mention` | hint | line | **new**: a bare flag no program precedes |
| `claim-anchor/missing-file` | certain | fix |  |
| `claim-anchor/missing-symbol` | certain | fix |  |
| `claim-anchor/unreadable` | hint | fix | an ignore comment would hide real breakage |
| `claim-anchor/unpinned` | hint (info) | pin |  |
| `claim-anchor/pinned-drift` | hint | pin |  |
| `doc-refs/unknown-dependency` | certain | fix |  |
| `change-binding/missing-affects` | certain | fix |  |
| `change-binding/unknown-component` | certain | fix | on an implemented RFC, fold it |
| `change-binding/touched-but-undeclared` | - | retired | on main, by the RFC-scope decision; `change verify` keeps the fact |
| `change-binding/declared-but-untouched` | - | retired | on main, by the RFC-scope decision; `change verify` keeps the fact |
| `requirement-grammar/mixed-disposition` | certain | fix | draft allowance |
| `requirement-grammar/empty-requirements` | certain | fix | draft allowance |
| `requirement-grammar/missing-id` | certain | fix | draft allowance |
| `requirement-grammar/invalid-id` | certain | fix | draft allowance |
| `requirement-grammar/duplicate-id` | certain | fix | draft allowance |
| `requirement-grammar/missing-provenance` | certain | fix | draft allowance |
| `requirement-grammar/invalid-provenance` | certain | fix | draft allowance |
| `requirement-grammar/missing-behavior` | certain | fix | draft allowance |
| `requirement-grammar/missing-scenario` | certain | fix | draft allowance |
| `requirement-grammar/incomplete-scenario` | certain | fix | draft allowance |
| `requirement-grammar/task-missing-id` | certain | fix | draft allowance |
| `requirement-grammar/task-multiple-references` | certain | fix | draft allowance |
| `requirement-grammar/task-misplaced-reference` | certain | fix | draft allowance |
| `requirement-grammar/task-empty-reference` | certain | fix | draft allowance |
| `requirement-grammar/empty-tasks` | certain | fix | draft allowance |
| `requirement-grammar/task-duplicate-id` | certain | fix | draft allowance |
| `requirement-grammar/task-unresolved-req` | certain | fix | draft allowance |
| `requirement-grammar/task-unresolved-component` | certain | fix | draft allowance |
| `duplicate-block/repeated-block` | certain | fix |  |
| `duplicate-block/copied-block` | hint | line |  |
| `code-references/unknown-command` | certain | fix |  |
| `code-references/unknown-option` | certain | fix |  |
| `code-references/unknown-symbol` | hint | line |  |
| `code-references/option-not-on-command` | certain | fix | reads option aliases, fixed on main |
| `code-references/unknown-env-var` | hint | line | a fenced line too, once the scan covers fences |
| `code-references/unknown-path` | hint | line | the same locally and in CI once `a-path-is-named-when-git-lists-it` is implemented |
| `test-ownership/unowned-test` | certain | fix | adoption-record allowance |
| `test-ownership/duplicate-test-owner` | certain | fix |  |
| `test-ownership/not-a-test` | certain | fix |  |
| `test-ownership/inexact-ownership` | certain | fix |  |
| `test-ownership/owned-test-missing` | certain | fix |  |
| `test-ownership/missing-test-root` | certain | fix |  |
| `test-ownership/ungoverned-test-file` | hint | fix | a root, an owner, `paths.test_patterns`, or a rename |
| `adoption-record/unreadable` | certain | fix |  |
| `adoption-record/source-unverifiable` | certain | fix | the checkout, as the finding says |
| `adoption-record/debt-not-at-source-revision` | certain | fix |  |
| `history-depth/shallow-clone` | certain | fix | the checkout |
| `history-depth/no-history` | hint | fix | the checkout, or `--only` checks that read no history |
| `co-change/unreflected-change` | hint | acknowledge (trailer) | subject: the doc |
| `co-change/acknowledged` | - | retired | an accepted finding keeps its own code |
| `co-change/invalid-acknowledgement` | - | retired | becomes `acknowledgement/invalid` |
| `co-change/unused-acknowledgement` | - | retired | becomes `acknowledgement/unused` |
| `diff-integrity/baseline-grew` | certain | acknowledge (trailer) | subject: the baseline path; the adopting change is exempt |
| `diff-integrity/adoption-record-grew` | certain | fix |  |
| `diff-integrity/adoption-source-rebound` | certain | fix |  |
| `diff-integrity/adoption-base-unreadable` | - | retired | merged into `base-config-unreadable` |
| `diff-integrity/adoption-debt-already-owned` | certain | fix |  |
| `diff-integrity/adoption-debt-not-managed` | certain | fix |  |
| `diff-integrity/adoption-pin-not-on-ref` | certain | fix | the checkout |
| `diff-integrity/adoption-record-removed` | certain | acknowledge (trailer) | subject: the record's path |
| `diff-integrity/adoption-debt-not-historical` | certain | fix |  |
| `diff-integrity/adoption-exception-revived` | certain | fix |  |
| `diff-integrity/adoption-debt-touched` | certain | fix | own the file |
| `diff-integrity/implemented-rfc-changed` | certain | fix | **changed**: a moved pin is no change |
| `diff-integrity/implemented-rfc-removed` | certain | acknowledge (trailer) | **new answer**; subject: the RFC's path |
| `diff-integrity/accepted-decision-removed` | certain | fix | deprecate it, then delete it in a later change |
| `diff-integrity/decision-rewritten` | hint | acknowledge (trailer) | a wording correction; a changed decision is superseded |
| `diff-integrity/owner-changed` | hint | acknowledge (trailer) | **narrowed**; subject: the moved file |
| `diff-integrity/check-disabled` | certain | acknowledge (trailer) | subject: the check, or `paths.docs_root` |
| `diff-integrity/layer-rule-disabled` | certain | acknowledge (trailer) | subject: the dotted name |
| `diff-integrity/source-excluded` | hint | acknowledge (trailer) | subject: the dotted name |
| `diff-integrity/extra-doc-removed` | hint | acknowledge (trailer) | subject: the dotted name |
| `diff-integrity/files-dropped` | certain | acknowledge (trailer) | **new**: a narrowing that drops files still on disk |
| `diff-integrity/base-config-unreadable` | hint (info) | fix | **changed**: only when no ancestor's config loads |
| `diff-integrity/gate-file-changed` | certain | acknowledge (trailer) | subject: the file's path |
| `diff-integrity/anchor-removed` | certain | acknowledge (trailer) | **new answer**; subject: `path#symbol` |
| `diff-integrity/claim-removed` | certain | acknowledge (trailer) | subject: the claim id |
| `diff-integrity/claim-downgraded` | hint | acknowledge (trailer) | **new**; subject: the claim id |
| `diff-integrity/governing-claim-changed` | certain | acknowledge (trailer) | subject: the claim id |
| `diff-integrity/governing-claim-removed` | certain | acknowledge (trailer) | subject: the claim id |
| `diff-integrity/claim-reworded` | hint | acknowledge (trailer) | **changed**: loses its record excuse |
| `diff-integrity/inventory-removed` | certain | acknowledge (trailer) | **new answer**; subject: `source#kind` |
| `diff-integrity/inventory-weakened` | certain | acknowledge (trailer) | subject: the doc's path |
| `diff-integrity/setting-weakened` | certain | acknowledge (trailer) | subject: the dotted name |
| `diff-integrity/unreviewed-setting-change` | hint | acknowledge (trailer) | subject: the dotted name |
| `diff-integrity/rules-narrowed` | hint | acknowledge (trailer) | subject: `surface.rules` or `frameworks.enabled` |
| `new-dependency/undeclared-new-dependency` | hint | fix | declaring the import states a fact |
| `ignore-comment/certain-finding` | certain | fix |  |
| `ignore-comment/unknown-check` | certain | fix |  |
| `ignore-comment/unused` | certain | fix | `unknown-path` no longer reads the disk once `a-path-is-named-when-git-lists-it` is implemented |
| `ignore-comment/unclosed-block` | certain | fix |  |
| `ignore-comment/unmatched-end` | certain | fix |  |
| `ignore-comment/no-reason` | certain | fix |  |
| `ignore-comment/wrong-answer` | certain | fix | **new**: names a code not declared `line` |
| `acknowledgement/invalid` | hint (info) | fix | **new**: a later commit carries a valid trailer |
| `acknowledgement/unused` | hint (info) | fix | **new**: lapses when the change merges |
| `rfc-structure/missing-weight` | certain | fix | draft allowance |
| `rfc-structure/missing-section` | certain | fix | draft allowance |
| `rfc-structure/section-out-of-order` | certain | fix |  |
| `rfc-structure/dense-paragraph` | hint | line | the paragraph's line |

`diff-integrity/files-dropped` covers a narrowing that removes something still present on
disk: a removed source root that still has files, a removed test root or emptied
`test_patterns` while test files exist, and an `extra_docs` entry whose file still exists. The
same narrowing of something already gone stays the hint it is today.

### Depends on

Six certain codes misread a correct tree. Five were corrected on main before the second history
reset: `links/unknown-anchor` (GitHub's slugger), `phantom-layer/hollow-layer` (content in
sub-folders), `supersession/status-not-deprecated` (`status: removed`),
`rfc-follow-through/missing-required-update-path` (`kind: create`) and
`code-references/option-not-on-command` (option aliases). The sixth, `ignore-comment/unused`
(`unknown-path` reading the disk, so a generated file differs locally and in CI), is corrected by
the small RFC `a-path-is-named-when-git-lists-it`, accepted with this one and implemented after
the records RFC below; its `fix` answer in the table holds once that lands.

This proposal also depends on
[Decision records govern what they decide](decision-records-govern-what-they-decide.md), which
makes decision records living topic docs, so that a change's sign-off is a commit trailer only.
Both were accepted on 2026-10-29, so the fallback this proposal kept for that RFC's rejection,
20 `diff-integrity/` rows reverting to a record and five answers, is gone.

### Scope

- The answers are general: any check, for any language, declares one per code, and the
  acknowledgement step serves any code declared `trailer`. Only the choice for each code is
  specific.
- The scaffolded workflow and the Action keep their default, certain findings alone: an
  adopter's tree is not held to this until its maintainers choose it.

### Cost and risk in full

- The code: one declaration per code, the declaration test and the runtime guard, the
  acknowledgement step with its misuse codes, a subject on each finding it can accept, the
  nine record tests deleted, four setting directions, the ignore-comment refusal and the
  pin-blind reading, the claim-downgrade rule, the base-config loader, the fenced-line
  coverage, the `unknown-mention` split, the glossary detector change, `co-change` reading the
  code repository's range, draft leniency in one place, and the task checkbox with its
  finding, its progress count and its reminder. Deleted: eight codes, two of them the
  `mtime-drift` check's, and `foreign`.
- Accepting this proposal qualifies five records in place, each with a dated item, and links
  the phrase it qualifies in each:
  [A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md)
  for its record excuse and a base config that does not load,
  [Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)
  for draft findings,
  [RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)
  for folding an implemented RFC, and
  [Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)
  for removed anchors and inventory entries, and
  [Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)
  for the `foreign` list. It carries a tombstone for `mtime-drift` and for each code this
  proposal retires.
- Four answers, each matching how long its finding lasts: a waiver as long as the mismatch, a
  trailer for one change, a pin until the content moves, a fix for good.
- Every finding a trailer accepts now prints one info line, so a reviewer sees from the run
  what was waved through.
- A decision record excuses no finding. The codes it excuses today take a trailer, and a
  trailer lapses when a later commit of the change touches the finding's file, so on a sealed
  file such as `irminsul.toml` it goes on the last commit that touches it.
- Raising `checks.external_links.ttl_hours` or `timeout_seconds`, changing `cache_path`, or
  setting `checks.schema_leak.protected_paths` becomes `setting-weakened`, certain, so an
  adopter's default gate fails on it until a trailer names it. Today it is a hint that gate
  passes.
- A re-read of an anchored doc takes two acts, the re-pin and a trailer.
- For a doc that owns Python code, `depends_on` means import dependencies only. An edge moved
  into the body is a weak reference, so `context`'s `depends_on` list and the strong-reference
  rules of `orphans` no longer see it.
- **Extending `co-change` closes the drift gap that deleting `mtime-drift` would open.** In the
  siblings layout, where the code lives in another repository, `co-change` read only the docs
  repository's range, and the scaffolded nightly workflow says the cross-repository drift
  signal lives in `mtime-drift`. Without the extension, a doc there whose paragraphs carry no
  anchor and whose claims pin no evidence would be asked about by nothing when its code moves.
  The extension has a cost of its own: the code repository's pull request must pass
  `source-diff`, as the scaffolded code-repository workflow already does, and answers a
  finding with a trailer in its own commits.
- An upgrading adopter that enabled `mtime-drift` must delete it, and its own `--diff` gate
  asks for a trailer naming it.
- An adopter that lists flags under `foreign` gets `frontmatter/retired-field` and moves each
  one to an ignore comment on the line that names it.
- `rfc-follow-through/all-tasks-done` is certain, so an adopter's default gate fails on an
  accepted RFC whose last task was just ticked until `change finalize` runs. An adopter whose
  task lists have no boxes sees nothing, because an RFC with no box is not tracked.
- An agent can tick a box without doing the work, and can leave one unticked after doing it;
  the recorded limitation above is the answer to both.
- The guard and the declaration test run in this repository's tests only; a check added by a
  fork is not held to them.

### Not chosen, in full

- **A YAML ignore comment on frontmatter entries.** Rejected by the owner: a fix answers
  `import-deps/hallucinated-dependency`, the one warning it would have served once
  `a-source-file-has-one-claim` retires `parent-child/wildcard-with-children`, and it would add
  a second comment grammar and a frontmatter comment reader.
- **One generic waiver keyed by subject for every line-less finding.** Rejected: it makes a
  change-scoped finding and a drift finding permanent, which is the rubber stamp the trailer
  and the pin exist to avoid.
- **Reporting `import-deps/hallucinated-dependency` at info**, as the earliest draft proposed.
  Rejected: an info line with no answer prints on every run.
- **Letting a `claims:` entry back a dependency no import shows.** Not chosen: it keeps such an
  edge in `depends_on` at the cost of a change to the check, where a linked sentence needs
  none.
- **A decision record as a second answer.** Rejected by decision 1: records become living topic
  docs under a separate RFC, not one change's sign-off, so a change's sign-off is a trailer
  only.
- **`mtime-drift` as a time finding, or at info.** Rejected by decision 7: as time it still
  fails the local gate that fails on time, answered only by an edit, and at info it prints with
  nothing to clear it. A doc-level pin was rejected earlier: the re-pin commit itself resets the
  doc's commit time.
- **A certain `base-config-unreadable` that needs a sign-off.** Rejected by decision 9.
- **Clearing `owner-changed` with a link between the two docs**, as the earlier draft proposed.
  Rejected: a link says nothing about the prose the old doc kept.
- **Sealing `foreign` instead of deleting it.** The alternative in decision 10.
- **A hand-kept table of answers in a doc or a test.** Rejected: it drifts from the checks,
  which is why each code's class already lives beside it. The table above is this proposal's
  record of the choices; the declarations replace it once implemented.
- **Flip the gate and let authors edit.** Rejected: it is the gaming the class decision
  refused.
- **Ticking in the pull request description.** Rejected: Irminsul reads only the repository
  and git, so a tick has to be in the RFC file, in the same diff as the code.
- **The reminder as a finding.** Rejected by decision 13: a change can touch a component
  without doing the RFC's work, so a wrong reminder is read and left, and a finding needs an
  answer.

### Left open

- `accepted-not-implemented` gives an RFC that legitimately waits only implement or reject, and
  one touch to the RFC silences it for good. A declared next-review date, like
  `target_decision_date`, is a later change.
- `retired-references/unmatched-generated-marker` duplicates
  `agents-manifest/missing-generated-markers` when that opt-in check is on; one marker parser
  is a later change.
- The audit found wrong reports outside the six certain bugs, each a check fix outside this
  proposal, and each takes its declared answer until then: `rules-narrowed` reads an added glob as a
  removal, `governing-claim-changed` fires on `planned` to `implemented` and on a renamed
  evidence file, `inventory-removed` counts a widened `source` as a removal, `source-excluded`
  reports removing a source root that does not exist, and `new-dependency` reads a pure rename
  as new imports.
- `inventory-drift` and `code-references` each decide which program a span invokes, and they
  disagree on a pipe; one rule for both is a later change.

## Requirements

### Requirement: Every code declares its answer
ID: every-hint-declares-answer
Provenance: code

Every hint and time code a check explains, info included, SHALL be declared `line`,
`trailer`, `pin` or `fix`, and a certain code SHALL be declared `trailer` or not at all; every
finding of a code declared `line` SHALL carry a line in a file the ignore-comment pass reads,
and every finding of a code declared `trailer` SHALL carry a subject.

#### Scenario: An undeclared code
- **WHEN** a check adds a hint code to its explanations without an answer
- **THEN** the declaration test fails

#### Scenario: An undeclared info code
- **WHEN** a check adds a hint code it reports only at info, without an answer
- **THEN** the declaration test fails

#### Scenario: An undeclared time code
- **WHEN** a check adds a time code to its explanations without an answer
- **THEN** the declaration test fails

#### Scenario: A certain code declared line
- **WHEN** a check declares a certain code `line`
- **THEN** the declaration test fails

#### Scenario: A line code without a line
- **WHEN** a code declared `line` is reported with no line in any test
- **THEN** the runtime guard fails that test

#### Scenario: A trailer code without a subject
- **WHEN** a code declared `trailer` is reported with no subject in any test
- **THEN** the runtime guard fails that test

### Requirement: A trailer acknowledges a code declared trailer
ID: trailer-pass
Provenance: code

An `Irminsul-Reviewed` trailer SHALL acknowledge a finding whose code is declared
`trailer` when its code, path, and subject match and neither a later commit of this change
nor uncommitted work touches a file the finding is about, reporting it at info under its own
code.

#### Scenario: A reviewed rewording
- **WHEN** a change rewords the claim `binding-is-additive` in `docs/components/checks.md` and a commit carries `Irminsul-Reviewed: diff-integrity/claim-reworded docs/components/checks.md binding-is-additive reason="..."`
- **THEN** that finding is reported at info under its own code

#### Scenario: A second claim in the same doc
- **WHEN** the same change also rewords another claim in that doc
- **THEN** that finding stays a warning

#### Scenario: A later commit
- **WHEN** a later commit of the same change edits `docs/components/checks.md` again
- **THEN** the rewording is a warning again

### Requirement: One step accepts trailers
ID: acknowledgement-step
Provenance: code

One acknowledgement step SHALL read the change's `Irminsul-Reviewed` trailers, accept a finding
only through the answer its code declares, by its code, path and subject, and report each
finding it accepts at info under its own code with the trailer's reason; no check SHALL test
for a decision record.

#### Scenario: A trailer accepts a weakened setting
- **WHEN** a change raises `checks.external_links.ttl_hours` from 168 to 720 and a commit carries `Irminsul-Reviewed: diff-integrity/setting-weakened irminsul.toml checks.external_links.ttl_hours reason="..."`
- **THEN** `diff-integrity/setting-weakened` is reported at info, quoting that reason

#### Scenario: No trailer
- **WHEN** the same change carries no such trailer
- **THEN** `diff-integrity/setting-weakened` is an error

#### Scenario: A trailer for a fix code
- **WHEN** a commit carries `Irminsul-Reviewed: diff-integrity/adoption-record-grew .irminsul-adoption.json reason="..."`
- **THEN** it accepts nothing and is reported as `acknowledgement/invalid`

#### Scenario: A decision record alone
- **WHEN** a change raises `checks.external_links.ttl_hours` from 168 to 720 and adds a stable decision record whose `## Decision` names `checks.external_links.ttl_hours` in a code span, with no trailer
- **THEN** `diff-integrity/setting-weakened` is an error

### Requirement: A setting with a direction is judged by it
ID: setting-directions
Provenance: code

The config seal SHALL report `diff-integrity/setting-weakened` when
`checks.schema_leak.protected_paths` is set or loses an entry, when
`checks.external_links.ttl_hours` or `checks.external_links.timeout_seconds` is raised, and
when `checks.external_links.cache_path` changes, and nothing when one of the first three moves
the other way; it SHALL report `diff-integrity/unreviewed-setting-change` only for a setting
with no direction.

#### Scenario: A tightened setting
- **WHEN** a change lowers `checks.external_links.ttl_hours` from 168 to 24
- **THEN** `diff-integrity` reports nothing about it

#### Scenario: A loosened setting
- **WHEN** a change raises `checks.external_links.ttl_hours` from 168 to 720 and carries no trailer naming it
- **THEN** `diff-integrity/setting-weakened` is an error

#### Scenario: A setting with no direction
- **WHEN** a change edits `frameworks.command_names`
- **THEN** `diff-integrity/unreviewed-setting-change` is reported, and a trailer naming `frameworks.command_names` accepts it

### Requirement: Each code takes only its declared answer
ID: one-answer-per-code
Provenance: code

An ignore comment SHALL waive a hint or time finding only when its code is declared `line`,
and SHALL be reported as `ignore-comment/wrong-answer` when it names a hint or time code
declared otherwise; a doc change that only moves pins SHALL NOT count as a change to that doc
for `co-change`.

#### Scenario: An ignore comment on pin drift
- **WHEN** an ignore comment naming `claim-anchor/pinned-drift`, with a reason, sits on a drifted anchor's line
- **THEN** the drift is still reported, and the comment is reported as `ignore-comment/wrong-answer`

#### Scenario: A re-pin alone
- **WHEN** a change edits an anchored function, and the only change to the doc that describes it is the re-pin of that anchor
- **THEN** `claim-anchor/pinned-drift` is not reported, and `co-change/unreflected-change` is

### Requirement: A claim downgrade is sealed
ID: sealed-narrowings
Provenance: code

`diff-integrity` SHALL report `diff-integrity/claim-downgraded`, a hint, when a claim whose
relation at the base is `review-on-divergence`, stated or omitted, becomes
`follows-evidence`, and a trailer naming the claim id SHALL answer it.

#### Scenario: A claim downgraded
- **WHEN** a change sets `relation: follows-evidence` on a claim that had no `relation`
- **THEN** `diff-integrity/claim-downgraded` is a warning, and a trailer naming the claim's id accepts it

#### Scenario: A downgraded claim removed later
- **WHEN** a later change removes a claim whose relation at its base is already `follows-evidence`
- **THEN** `diff-integrity` reports nothing about it

### Requirement: The glossary detector agrees with its fixer
ID: glossary-detector-matches-fixer
Provenance: code

`glossary-discipline/unlinked-term` SHALL be reported for a doc only when a use of the term
lies outside code, comments, headings and links, the text that `irminsul fix` links, and SHALL
be reported at info.

#### Scenario: A term only in a link's text
- **WHEN** a doc uses "RFC" only as the text of links to RFC docs, and no link of its reaches the glossary entry
- **THEN** `glossary-discipline/unlinked-term` is not reported for it

#### Scenario: A term only in a heading
- **WHEN** a doc's only use of "RFC" is its heading `# RFCs`
- **THEN** `glossary-discipline/unlinked-term` is not reported for it

#### Scenario: A term in prose
- **WHEN** a doc uses "RFC" in a sentence, and no link of its reaches the glossary entry
- **THEN** `glossary-discipline/unlinked-term` is reported at info, and `irminsul fix --only glossary-discipline --confirm` links that use

### Requirement: The pull-request gate fails on hints
ID: gate-fails-on-hints
Provenance: adr

This repository's pull-request gate SHALL run `irminsul check --diff` with
`--fail-on hint`, and failing on hints SHALL not include a finding the draft exemption
demoted; the draft exemption SHALL be the only place a draft changes which findings are
reported or at what severity.

#### Scenario: An accepted draft RFC on main
- **WHEN** a draft RFC with incomplete requirements is on the main branch
- **THEN** the gate does not fail on its demoted findings

#### Scenario: A draft INDEX with no content docs
- **WHEN** a layer folder holds only a draft `INDEX.md`
- **THEN** `phantom-layer/hollow-layer` is reported as a warning the gate does not fail on, and `phantom-layer/layer-under-construction` is not reported

### Requirement: A trailer answers folding an implemented RFC
ID: implemented-rfc-removal-answered
Provenance: code

A trailer SHALL accept `diff-integrity/implemented-rfc-removed` when it names the path at the
base of the implemented RFC that is gone; `diff-integrity/implemented-rfc-changed` SHALL
compare an implemented RFC with its pins left out, and SHALL still be reported for any other
edit.

#### Scenario: A folded RFC
- **WHEN** a change deletes `docs/rfcs/a-gate-file-is-sealed-not-scored.md`, implemented at the base, and a commit carries `Irminsul-Reviewed: diff-integrity/implemented-rfc-removed docs/rfcs/a-gate-file-is-sealed-not-scored.md reason="..."`
- **THEN** `diff-integrity/implemented-rfc-removed` is reported at info, quoting that reason

#### Scenario: A deletion with no trailer
- **WHEN** the same change carries no such trailer
- **THEN** `diff-integrity/implemented-rfc-removed` is an error

#### Scenario: A re-pin inside an implemented RFC
- **WHEN** the only change to an implemented RFC moves the pin of one of its anchors
- **THEN** `diff-integrity/implemented-rfc-changed` is not reported

#### Scenario: A typo in an implemented RFC
- **WHEN** a change fixes a typo in an implemented RFC's prose and a commit carries `Irminsul-Reviewed: diff-integrity/implemented-rfc-changed docs/rfcs/a-gate-file-is-sealed-not-scored.md reason="typo"`
- **THEN** `diff-integrity/implemented-rfc-changed` is an error, and the trailer is reported as `acknowledgement/invalid`

### Requirement: A trailer answers a removed anchor or inventory entry
ID: removed-governance-answered
Provenance: code

A trailer SHALL accept `diff-integrity/anchor-removed` when it names the anchor as
`path#symbol`, and `diff-integrity/inventory-removed` when it names the entry as
`source#kind`.

#### Scenario: A pruned paragraph
- **WHEN** a change deletes a paragraph of `docs/components/checks.md` with its anchor on `src/irminsul/checks/base.py#CheckFlag.opt_in`, which still resolves, and a commit carries `Irminsul-Reviewed: diff-integrity/anchor-removed docs/components/checks.md src/irminsul/checks/base.py#CheckFlag.opt_in reason="..."`
- **THEN** `diff-integrity/anchor-removed` is reported at info, quoting that reason

#### Scenario: A pruned paragraph with no trailer
- **WHEN** the same change carries no such trailer
- **THEN** `diff-integrity/anchor-removed` is an error

#### Scenario: One of two entries on one source
- **WHEN** a change deletes the `cli-options` entry of `docs/components/cli.md`, keeps its `cli` entry on the same source, and a commit carries `Irminsul-Reviewed: diff-integrity/inventory-removed docs/components/cli.md src/irminsul/cli.py#cli-options reason="..."`
- **THEN** `diff-integrity/inventory-removed` is reported at info, quoting that reason, and the `cli` entry is judged as before

### Requirement: A base config that does not load is compared through an earlier one
ID: base-config-nearest-ancestor
Provenance: code

When the `irminsul.toml` at the base does not load, `diff-integrity` SHALL compare the change,
in both the config seal and the adoption seal, with the newest earlier version of
`irminsul.toml` that loads, and SHALL report `diff-integrity/base-config-unreadable`, at info,
only when no earlier version loads.

#### Scenario: A repairing change
- **WHEN** the base `irminsul.toml` is not valid TOML, the version before it loads, and the change repairs the file
- **THEN** nothing is reported about the base config

#### Scenario: A weakening beside the repair
- **WHEN** the same change also raises `checks.parent_child.length_warning_lines` above its value in the version that loads, and carries no trailer naming it
- **THEN** `diff-integrity/setting-weakened` is an error

#### Scenario: No earlier version loads
- **WHEN** no version of `irminsul.toml` at or before the base loads, and the adoption record holds entries
- **THEN** `diff-integrity/base-config-unreadable` is reported at info, and `diff-integrity/adoption-base-unreadable` is not reported

### Requirement: `mtime-drift` is retired
ID: mtime-drift-retired
Provenance: code

`mtime-drift` SHALL NOT be a registered check, its codes and the setting
`overrides.mtime_drift_days` SHALL be gone, and a stable decision record SHALL declare a
`retires:` tombstone for it, so `retired-references` reports current guidance that presents
it as live.

#### Scenario: An old doc
- **WHEN** a source file a doc claims was committed 40 days after the doc, and no change in the range touches either
- **THEN** `irminsul check --fail-on hint,time` reports nothing about it

#### Scenario: A config that still enables it
- **WHEN** `irminsul.toml` lists `mtime-drift` in `checks.enabled`
- **THEN** the config does not load, and the error names `mtime-drift`

#### Scenario: A live mention
- **WHEN** a stable component doc says in a sentence that `mtime-drift` reports old docs, and does not link the record that retires it
- **THEN** `retired-references/retired-reference` is reported on that line

### Requirement: `co-change` reads the source repository's range
ID: co-change-source-range
Provenance: code

When a run is given `--source-diff` beside `--diff`, `co-change` SHALL also read the source
repository's range and report `co-change/unreflected-change` on a doc that claims a file that
range changed, as it does for a file the docs repository's range changed, and a trailer on a
commit of the source repository's range SHALL acknowledge it.

#### Scenario: A code change in the other repository
- **WHEN** in the `siblings` layout a pull request changes `core.py` in the code repository, a docs-repository doc claims `core.py` in `describes`, and the run is `irminsul check --diff HEAD --source-diff origin/main`
- **THEN** `co-change/unreflected-change` is reported on that doc

#### Scenario: A trailer in the code repository
- **WHEN** a commit of the same pull request in the code repository carries `Irminsul-Reviewed: co-change <doc> reason="..."`, naming that doc
- **THEN** `co-change/unreflected-change` is reported at info under its own code, quoting that reason

#### Scenario: No source range
- **WHEN** the same code repository change is run with `--diff HEAD` and no `--source-diff`
- **THEN** `co-change` reports nothing about `core.py`

### Requirement: An ignore comment covers a fenced block
ID: fenced-lines-ignorable
Provenance: code

A standalone ignore comment directly above a fenced block SHALL cover every line of that block,
and an `ignore-start` and `ignore-end` pair SHALL cover the fenced lines between them; a
comment written inside a fence SHALL NOT be read.

#### Scenario: A comment above a fence
- **WHEN** a standalone ignore comment naming `code-references/unknown-env-var`, with a reason, stands directly above a fenced block whose third line names an environment variable no source reads
- **THEN** that finding is not reported, and the comment is not reported as unused

#### Scenario: A comment inside a fence
- **WHEN** a fenced example contains an ignore comment
- **THEN** it covers nothing and is not reported

### Requirement: The warnings that carry no line get an answer
ID: line-less-warnings-answered
Provenance: code

`diff-integrity/decision-rewritten` SHALL be acknowledged by a trailer naming the record;
`diff-integrity/owner-changed` SHALL be reported only while the old owner's body still names
the moved file, on that doc, and SHALL be acknowledged by a trailer naming the file;
`rfc-follow-through/stable-doc-links-draft-rfc` SHALL carry the line of its link; and
`import-deps` SHALL count a call of `importlib.import_module` with a string literal as an
import.

#### Scenario: A typo in a decision
- **WHEN** a change fixes a typo in the `## Decision` of `docs/decisions/finding-classes-decide-what-blocks.md` and a commit carries `Irminsul-Reviewed: diff-integrity/decision-rewritten docs/decisions/finding-classes-decide-what-blocks.md reason="typo"`
- **THEN** that finding is reported at info under its own code

#### Scenario: A clean split
- **WHEN** a change moves `src/irminsul/fix.py` from one doc's `describes` to another's, and the old doc's body no longer names it
- **THEN** `diff-integrity/owner-changed` is not reported

#### Scenario: A leftover mention
- **WHEN** the old doc's body still names `src/irminsul/fix.py` in a sentence
- **THEN** `diff-integrity/owner-changed` is a warning on the old doc, with `src/irminsul/fix.py` as its subject

#### Scenario: A link to a draft RFC
- **WHEN** a stable doc links a draft RFC on line 40, and a standalone ignore comment naming `rfc-follow-through/stable-doc-links-draft-rfc`, with a reason, stands on line 39
- **THEN** that finding is not reported

#### Scenario: A dynamic import
- **WHEN** a doc's Python file calls `importlib.import_module` with the dotted name, as a string literal, of a module another doc owns, and lists that doc in `depends_on`
- **THEN** `import-deps/hallucinated-dependency` is not reported for it

### Requirement: A narrowing that drops files on disk is certain
ID: narrowing-of-present-files-is-certain
Provenance: code

`diff-integrity/files-dropped`, certain, SHALL be reported when a change removes a source root
that still holds files, removes a test root or empties `paths.test_patterns` while test files
exist, or removes an `extra_docs` entry whose file still exists, and a trailer naming the
setting's dotted name SHALL accept it.

#### Scenario: A removed root with files
- **WHEN** a change removes `src` from `paths.source_roots` while `src/irminsul/cli.py` exists, and carries no trailer naming `paths.source_roots`
- **THEN** `diff-integrity/files-dropped` is an error

#### Scenario: An extra doc removed with its file
- **WHEN** a change removes an `extra_docs` entry together with the file it named
- **THEN** `diff-integrity/files-dropped` is not reported, and `diff-integrity/extra-doc-removed` is a warning that a trailer naming `paths.extra_docs` accepts

### Requirement: Two codes that judge meaning are hints
ID: meaning-codes-are-hints
Provenance: code

A flag in a code span that no program name precedes SHALL be reported as
`inventory-drift/unattributed-mention`, a hint declared `line`, while a flag in a span that
invokes this project's program SHALL stay `inventory-drift/unknown-mention`, certain; and
`schema-leak/pattern-match` SHALL be a hint declared `line`.

#### Scenario: A bare git flag
- **WHEN** a stable doc names `--no-verify` alone in a code span, and a standalone ignore comment naming `inventory-drift/unattributed-mention`, with a reason, stands on the line above
- **THEN** nothing is reported

#### Scenario: A flag of our own program
- **WHEN** a stable doc's code span invokes this project's program with a flag its CLI does not declare
- **THEN** `inventory-drift/unknown-mention` is an error

#### Scenario: A user's model in a fence
- **WHEN** a components doc shows a user's Pydantic model in a python fence, and a standalone ignore comment naming `schema-leak/pattern-match`, with a reason, stands directly above the fence
- **THEN** nothing is reported

### Requirement: The `foreign` list is retired
ID: foreign-list-retired
Provenance: code

An inventory entry's `foreign` field SHALL be reported as `frontmatter/retired-field`, whose
suggestion names an ignore comment on the line, and no check or listing SHALL read it.

#### Scenario: An entry that still lists a foreign flag
- **WHEN** a doc's `cli-options` inventory entry lists a flag under `foreign`
- **THEN** `frontmatter/retired-field` is an error naming `foreign`, and the flag is judged as if the list were absent

### Requirement: The cached-link count is part of the summary
ID: cached-results-in-summary
Provenance: code

`external-links` SHALL report how many results came from the cache, and the oldest
observation among them, in the run's summary and SHALL NOT report them as a finding.

#### Scenario: A run that reads the cache
- **WHEN** a run reads three link results from the cache
- **THEN** no `external-links/cached-results` finding is reported, and the summary gives the count 3 and the oldest observation's time

### Requirement: A task can carry a checkbox
ID: task-checkboxes-parse
Provenance: code

A `## Tasks` item SHALL accept `[ ]`, `[x]` or `[X]` between its bullet and its backticked id,
reading the first as an open task and the others as a done one, and its id, text and reference
SHALL read as they do without the box.

#### Scenario: A ticked task
- **WHEN** an RFC's `## Tasks` holds the item `` - [x] `T1` Write the parser. (req: task-checkboxes-parse) ``
- **THEN** `T1` is done, its text is "Write the parser." and its requirement is `task-checkboxes-parse`

#### Scenario: An open task
- **WHEN** the same item opens with `[ ]` instead
- **THEN** `T1` is open, and its text and requirement are the same

#### Scenario: A box without an id
- **WHEN** an item is `- [x] Write the parser.`, with no backticked id
- **THEN** `requirement-grammar/task-missing-id` is reported for it

### Requirement: Ticking the last task asks for finalization
ID: all-tasks-done-finalizes
Provenance: code

`rfc-follow-through` SHALL report `rfc-follow-through/all-tasks-done`, certain, with the message
"every task is done: run `irminsul change finalize`", on an accepted RFC that has at least one
task, no task item that fails to parse and every task ticked; `change finalize` and
`change status` SHALL NOT treat it as a blocker.

#### Scenario: The last box ticked
- **WHEN** an accepted RFC has three tasks, `T1` and `T2` ticked at the base, and a change ticks `T3`
- **THEN** `rfc-follow-through/all-tasks-done` is an error on that RFC

#### Scenario: A task still open
- **WHEN** an accepted RFC has one task unticked
- **THEN** `rfc-follow-through/all-tasks-done` is not reported

#### Scenario: A draft or an implemented RFC
- **WHEN** a draft RFC, or an implemented one, has every task ticked
- **THEN** `rfc-follow-through/all-tasks-done` is not reported

#### Scenario: Finalizing
- **WHEN** an accepted RFC has every task ticked and `irminsul change finalize` runs on it
- **THEN** the finding is not among its blockers, and `change status` does not list it as one

### Requirement: `change status` reports task progress
ID: status-shows-task-progress
Provenance: code

`change status` SHALL report how many of an RFC's tasks are done, as "4 of 7 tasks done", from the
ticks in the RFC alone and whether or not a diff baseline resolves, and its JSON SHALL carry each
task's done state and the count.

#### Scenario: Progress
- **WHEN** an accepted RFC has seven tasks, four of them ticked
- **THEN** `change status` reports "4 of 7 tasks done"

#### Scenario: No diff baseline
- **WHEN** the same RFC is read where no diff baseline resolves
- **THEN** it still reports "4 of 7 tasks done", and the evidence counts are unknown

#### Scenario: JSON
- **WHEN** `change status --format json` runs on the same RFC
- **THEN** each task item says whether it is done, and the tasks summary holds the count 4

### Requirement: The review queue names the RFC a change may serve
ID: review-queue-names-rfc-work
Provenance: code

`list review --changed` and `context --after-edit` SHALL list each accepted RFC that declares a
component the change touched and has an open task, with those tasks and the words "if this is its
work, tick the task", and SHALL list none for a change that touched no declared component; the
reminder SHALL NOT be a finding and SHALL NOT change a run's exit status.

#### Scenario: A change in a declared component
- **WHEN** an accepted RFC declares the component `checks`, its tasks `T2` and `T3` are open, and a change edits `src/irminsul/checks/rfc_follow_through.py`
- **THEN** `list review --changed` and `context --after-edit` each list the RFC with `T2` and `T3` and "if this is its work, tick the task"

#### Scenario: A change that touches no declared component
- **WHEN** the same change touches only `src/irminsul/orient.py`, whose component that RFC does not declare
- **THEN** neither lists the RFC

#### Scenario: An RFC with nothing open
- **WHEN** every task of that RFC is ticked and a change edits `src/irminsul/checks/rfc_follow_through.py`
- **THEN** neither lists the RFC

#### Scenario: A reminder is not a finding
- **WHEN** the reminder is printed
- **THEN** `irminsul check --fail-on hint,time` reports nothing about it, and the run's exit status is what it would be without the reminder

### Requirement: A task without a checkbox stays valid
ID: old-style-tasks-stay-valid
Provenance: code

A task item with no checkbox SHALL stay valid and count as open; an RFC none of whose tasks has a
checkbox SHALL be reported by `change status` as not tracked instead of as zero done, and SHALL NOT
raise `rfc-follow-through/all-tasks-done`.

#### Scenario: An implemented RFC written before checkboxes
- **WHEN** an implemented RFC's `## Tasks` holds three items, none with a checkbox
- **THEN** `requirement-grammar` reports nothing new about them, and `change status` reports its tasks as not tracked rather than "0 of 3 tasks done"

#### Scenario: A mixed list
- **WHEN** an accepted RFC ticks `T1` and `T2` and its `T3` has no checkbox
- **THEN** `T3` counts as open, `change status` reports "2 of 3 tasks done", and `rfc-follow-through/all-tasks-done` is not reported

## Tasks

- `T1` Declare `answers` on every check, print it in `explain` and in each suggestion, name the four answers in the agent protocol, and add the declaration test and the runtime guard. (req: every-hint-declares-answer)
- `T2` Move the trailer out of `co-change` into the acknowledgement step in the shared runner, with subjects and its own misuse codes, and retire co-change's three trailer codes. (req: trailer-pass)
- `T4` Report a narrowing that drops files still on disk as `diff-integrity/files-dropped`, certain and declared `trailer`. (req: narrowing-of-present-files-is-certain)
- `T5` Give `index-too-long` the line of the INDEX's first heading. (req: every-hint-declares-answer)
- `T6` Leave draft-demoted findings out of what `--fail-on hint` fails on. (req: gate-fails-on-hints)
- `T7` Delete the nine record tests in `diff-integrity`, so the step's trailers answer what a decision record answers today. (req: acknowledgement-step)
- `T8` Give the four settings their directions in `_SEALS`. (req: setting-directions)
- `T9` Refuse an ignore comment on a code not declared `line`, and read docs with pins left out for `co-change` and `decision-rewritten`. (req: one-answer-per-code)
- `T10` Report a claim downgraded to `follows-evidence`, first shown by a planted test. (req: sealed-narrowings)
- `T11` Read the glossary body through the fixer's masking in the detector, then link the remaining terms with `irminsul fix --confirm` and re-pin any claim whose evidence that edit touched. (req: glossary-detector-matches-fixer)
- `T12` Prove `certain_severity` dead with a planted test and delete it, move `hollow-layer` into `drafts_exempt` and retire `layer-under-construction`, and declare the `code-references` draft skip. (req: gate-fails-on-hints)
- `T13` Declare `implemented-rfc-removed` `trailer` with the RFC's path as its subject, and compare implemented RFCs through the pin-blind reading. (req: implemented-rfc-removal-answered)
- `T14` Give `anchor-removed` and `inventory-removed` their subjects and declare both `trailer`. (req: removed-governance-answered)
- `T15` Read the base config through one loader that falls back to the newest earlier version that loads, and merge `adoption-base-unreadable` into `base-config-unreadable` at info. (req: base-config-nearest-ancestor)
- `T16` Delete `mtime-drift`, its setting and its seal, remove it from `checks.enabled`, add its tombstone to the accepting record, and reword or link every live mention. (req: mtime-drift-retired)
- `T17` Let a standalone ignore comment above a fence, and a block around one, cover fenced lines, first shown by a planted test. (req: fenced-lines-ignorable)
- `T18` Give `decision-rewritten` and `owner-changed` their trailers, narrow `owner-changed` through `_moved_file_sentences`, give `stable-doc-links-draft-rfc` its line, and read literal `importlib` imports in `imported_paths`. (req: line-less-warnings-answered)
- `T19` Report a bare flag as `inventory-drift/unattributed-mention` and make `schema-leak/pattern-match` a hint, both declared `line`. (req: meaning-codes-are-hints)
- `T20` Retire the `foreign` field, delete its readers in `listing/command.py` and `listing/review.py`, and remove this repository's list from `docs/components/cli.md`. (req: foreign-list-retired)
- `T21` Move the cached-link count into the run summary and retire `external-links/cached-results`. (req: cached-results-in-summary)
- `T22` Make `co-change` read `ChangeRange.source_changed` and the trailers of the source repository's range under `--source-diff`, and reword the private-docs guide's scope note that sends a reader to `mtime-drift` for the cross-repository signal. (req: co-change-source-range)
- `T23` Read a leading `[ ]`, `[x]` or `[X]` on a task item into a field of `Task` that is empty without a box, and leave the id, text and reference reading as it is. (req: task-checkboxes-parse)
- `T24` Report `rfc-follow-through/all-tasks-done` from `RfcFollowThroughCheck` as one predicate in `gate.py`, judged but not raised when finalizing, certain and with no trailer. (req: all-tasks-done-finalizes)
- `T25` Carry the done state in `TaskItem` and `TaskSummary`, and print "N of M tasks done" in `change status` and its JSON. (req: status-shows-task-progress)
- `T26` List an accepted RFC's open tasks in `list review --changed` and `context --after-edit` when the change's footprint holds a component it declares, without making it a finding. (req: review-queue-names-rfc-work)
- `T27` Count a task with no box as open, report an RFC with no box as not tracked, and keep it out of the finding. (req: old-style-tasks-stay-valid)
- `T28` Show the box in the `new rfc` scaffold, write the tick flow into step 4 of the agent protocol, and qualify the sentence in the change doc that says a task carries no status. (req: all-tasks-done-finalizes)

## Resolution

Accepted by the owner on 2026-10-29, with the answers recorded under Decisions, and resolved by
[Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md), which states that every finding code declares one answer. Each other record that
governs code this proposal changes states its part, as accepted and not yet implemented, with a
dated item under its Changes: [A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md) the acknowledgement step; [A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md) the trailer in place of
the record excuse, the setting directions and the base config; [A baseline holds certain findings and grows only by decision](../decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md) the baseline's growth;
[Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md) removed governance and the claim downgrade; [Docs are atoms in six layers, and code has one owner](../decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md) `owner-changed`, the adoption record
and the glossary; [RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md) folding an implemented RFC and task checkboxes; [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) the
cached-link notice; and [Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md) the `foreign` list. No record was added.
