---
id: rfcs-have-four-states-and-git-history-seals-decided-records
title: "RFCs have four states, and git history seals decided records"
status: stable
describes: []
summary: Records are named by slug and have a fixed shape, an RFC opens with an owner's part and moves through four states that repository evidence can contradict, the change commands judge its scope, the protected branch's history seals implemented RFCs and accepted decisions, and retirements are tombstones.
governs:
  - src/irminsul/change/**
  - src/irminsul/checks/rfc_lifecycle.py
  - src/irminsul/checks/rfc_follow_through.py
  - src/irminsul/checks/rfc_structure.py
  - src/irminsul/checks/requirement_grammar.py
  - src/irminsul/checks/change_binding.py
  - src/irminsul/checks/retired_references.py
  - src/irminsul/checks/adr_structure.py
  - src/irminsul/checks/sections.py
  - src/irminsul/new/templates/adr.md.j2
  - src/irminsul/new/templates/rfc.md.j2
  - src/irminsul/new/command.py#_slugify
  - src/irminsul/new/command.py#resolve_destination
  - src/irminsul/cli.py#new_rfc
  - src/irminsul/frontmatter.py#RfcStateEnum
  - src/irminsul/frontmatter.py#RetirementEntry
  - src/irminsul/docgraph_index.py#parse_requirements
  - src/irminsul/docgraph_index.py#parse_tasks
  - src/irminsul/docgraph_index.py#_parse_task_bullet
  - src/irminsul/checks/diff_integrity.py#_sealed_records
  - src/irminsul/checks/diff_integrity.py#_sealed_rewrites
  - src/irminsul/checks/diff_integrity.py#_renamed_record
  - src/irminsul/checks/diff_integrity.py#_only_retargeted
  - src/irminsul/checks/diff_integrity.py#_retarget
  - src/irminsul/checks/diff_integrity.py#_decision_wording
retires:
  - id: split-rfc-checks
    kind: concept
    matches:
      - rfc-resolution
      - decision-updates
      - rfc-lifecycle-integrity
    guidance: Enable `rfc-lifecycle` and `rfc-follow-through` in checks.enabled.
  - id: frozen-hash-seal
    kind: concept
    matches:
      - frozen_hash
      - frozen-content-changed
      - missing-frozen-hash
      - premature-frozen-hash
      - sealed-rfc-changed
    guidance: An implemented RFC is immutable once `main` records it as implemented; `diff-integrity` compares it with the merge base under `--diff`.
  - id: diff-wide-rfc-scope
    kind: concept
    matches:
      - change-binding/touched-but-undeclared
      - change-binding/declared-but-untouched
    guidance: Run `irminsul change verify <rfc>`, which compares the change with that RFC's `affects` and blocks on `unreconciled-scope`; `irminsul change finalize <rfc>` refuses the same way.
---

# RFCs have four states, and git history seals decided records

## Status

Accepted, 2026-10-28.

## Context

An RFC that says "accepted" or "implemented" is useful only if repository evidence can
contradict it. A record cannot vouch for itself: a hash stored in the file it hashes is
recomputed by whoever edits it. The merge base can, because a pull request cannot change what
the protected branch holds. Numbered records collide silently when two branches pick one number
under different filenames, and invite prose such as "ADR-0029" that names a record without
linking it. And records accumulate, most of them restating shipped behaviour.

An RFC has two readers. The owner decides whether it should happen and what it needs from
them; the agent implements it and needs every name. The template mixed the two, so an owner
approved a draft only after asking for a summary of it, and the questions for the owner came
last.

Under `--diff`, `change-binding` compared the components a change touched with the union of
every accepted RFC's `affects`. A pull request is for one RFC, and a tree cannot say which, so
the union was the wrong thing to compare with. A fix to five checks reported three warnings
because an unrelated accepted RFC declared nine components, and the warning had no line to
ignore, so the only advice it offered, to add the components to that RFC's `affects`, would
have recorded something false.

## Decision

- **A record is named by the slug of its title.** `irminsul new adr "Cache sharding"` writes
  `cache-sharding.md` in the decisions layer, with that slug as its `id`; `new rfc` does the
  same for RFCs. `new` refuses a slug whose file exists, unless `--force`, or that another doc
  uses as its id, so two branches that pick one collide on one path. A record has no number or
  creation date, and prose names it by a link, which `links` checks.
- **ADRs have a fixed shape:** Status, Context, Decision, Alternatives Considered and
  Consequences. `adr-structure` reports a missing or duplicate section and an empty
  `## Decision`. The body Status is a human summary, never lifecycle evidence.
- **Four states.** `rfc_state` is `draft`, `accepted`, `implemented` or `rejected`, and nothing
  infers it; `rfc-lifecycle` reports an RFC without one. `change transition` applies a person's
  decision to `accepted` or `rejected`, and acceptance needs a `resolved_by` naming an existing
  doc. `change finalize` is the only path to `implemented`: it promotes each requirement into
  its owning component doc as a claim, anchored when its provenance is code, and writes the
  `implements` back-links. Both print their plan and write nothing without `--confirm`.
- **Every RFC declares `weight: small` or `weight: large`** in its frontmatter. The author
  proposes it and the owner may change it; no check guesses it.
- **The owner's part comes first.** A small RFC, a sign-off read in 5 to 30 seconds, has
  `## Summary` (what changes and what is signed off) and `## Decisions`. A large RFC, one that
  changes a decision or the foundation, breaks adopters, adds or removes a check or a command,
  or migrates data or history, has `## Summary`, `## Problem`, `## How it works`,
  `## Cost and risk` and `## Decisions`, and reads in about two minutes. The Summary ends with
  how many decisions wait for the owner.
- **The owner's part is written for a person:** plain words, terms defined where they appear,
  one worked example, and a code span only where the exact name matters.
- **The agent's part starts at `## Design detail`** and holds every list of names, files, ids
  and migration steps, then `## Requirements` and `## Tasks`.
- **`rfc-structure` reports** a missing weight, a missing or empty owner's section the weight
  requires, and an owner's section placed after `## Design detail`, in a draft or accepted
  RFC; and, as a hint, an owner's paragraph with four or more code spans.
- **This repository's two implemented RFCs are written in the layout**, rewritten at the
  second history reset once the check existed.
- **Evidence is derived, never stored.** Changed files, owners, tests and blockers come from
  the diff and the graph on every call, and a report never says behaviour is correct.
- **Behaviour-changing RFCs carry requirements and tasks:** a requirement has a stable id,
  SHALL or MUST text, WHEN/THEN scenarios and a `Provenance:`; a task may reference one
  requirement or component.
- **Updates follow the state.** An accepted RFC declares `required_updates`; the `implements`
  back-link is due once it is implemented, and `rfc-lifecycle` rejects one earlier.
- **Integrity and follow-through are separate checks.** `rfc-lifecycle` holds what makes a
  record untrustworthy, such as a dangling `resolved_by` or evidence before finalization;
  `rfc-follow-through` holds outstanding work, some of which `irminsul fix` completes.
- **Relationships are forward-only:** an RFC's own `supersedes` and `depends_on` say what it
  follows, and nothing edits a predecessor.
- **The change commands judge an RFC's scope.** `check --diff` does not compare a change with
  the RFCs' declared scope; `change-binding` keeps its shape rules,
  `change-binding/missing-affects` and `change-binding/unknown-component`, which judge the tree.
  `change verify` and `change finalize`, which are given the one RFC the change is for, report
  source in a component its `affects` leaves out as `unreconciled-scope`, and finalization
  refuses it. `change-binding/touched-but-undeclared` and `change-binding/declared-but-untouched`
  are removed.
- **History is the seal.** An RFC is implemented once the protected branch records it, which
  `change finalize` writes in the implementation's pull request. Under `--diff`, an RFC
  implemented at the merge base that differs is `diff-integrity/implemented-rfc-changed`, and one
  that is gone `implemented-rfc-removed`, both certain, so an extension starts a new RFC. An
  accepted decision record that is gone is `accepted-decision-removed`, certain, and its
  `## Decision` rewritten in place is `decision-rewritten`, a hint.
- **A re-pin does not rewrite an accepted record.** `diff-integrity/decision-rewritten`
  compares a `## Decision` section with each anchor's pin left out, so re-pinning an anchor
  that record holds, as a pin-format migration does, leaves its seal intact; where the anchor
  points still counts.
- **A rename is not a change.** A record gone from its old path is not reported when another
  holds the same text apart from its `id`. An implemented RFC whose only edits retarget
  references to docs the same change renamed, by repo-relative path, relative path, or id where
  the id is the filename, is unchanged. Any other retarget is a change.
- **Parallel work never moves a sealed record:** two branches adding one name collide on the
  unsealed newcomer, which the later branch renames.
- **Retirements are tombstones.** A stable decision record declares each retired command or
  concept under `retires:`, with exact `matches`, `guidance`, and a `surface_identity` for a CLI
  command. `retired-references` reports current guidance presenting one as live unless the
  phrase links to that record.
- **A settled RFC folds into the record that governs what it changed.** In a change a person
  merges deliberately, an implemented or rejected RFC is folded into the decision record that
  governs the code it changed, and its file is removed; git history keeps the original. Open
  proposals stay.
- **A decision record governs what it decides** (accepted; the lists are written, their checks
  are not yet implemented). Its `governs:` lists the files, parts of files, components, checks
  and settings it decides, a setting by its dotted name in the config schema. A stable record
  with no entry is `adr-structure/missing-governs`, and an entry that resolves to nothing
  `adr-structure/unresolved-governs`; a principle with no code of its own belongs in the
  foundation's principles.
- **A decision record is a living topic** (accepted, not yet implemented). A changed rule is
  edited in place, with one dated item in a closing `## Changes` section, oldest first and never
  edited once merged, which `adr-structure/malformed-changes`, `diff-integrity/changes-rewritten`
  and `diff-integrity/change-unrecorded` hold. A rewritten Decision is
  `diff-integrity/decision-rewritten`, certain, and a stable record deleted or no longer stable
  is `accepted-decision-removed`; a commit trailer answers both. A new decision goes into the
  record that governs what it changes: `change transition <rfc> accepted` appends the dated item
  there and refuses a `resolved_by` outside the decisions layer, and `irminsul new adr` writes a
  new record, with its `governs:`, only for something no record governs. This replaces the hint
  and the superseding record of "History is the seal" above.
- **A trailer answers removing an implemented RFC** (accepted, not yet implemented), naming its
  path at the base, so folding one into a decision record has an answer; editing one stays
  sealed, and a moved pin is no edit for `implemented-rfc-changed`.
- **Tasks carry checkboxes** (accepted, not yet implemented). `- [x]` marks a task done and
  `change status` counts them. An accepted RFC whose every task is ticked is
  `rfc-follow-through/all-tasks-done`, certain, which `change finalize` answers and which never
  blocks finalization. When a change touches a component an accepted RFC affects,
  `list review --changed` and `context --after-edit` print its open tasks as a reminder, not a
  finding. A tick is the agent's statement, which review and the owner check.
  `rfc-follow-through/stable-doc-links-draft-rfc` carries the line of its link, so an ignore
  comment answers it.

## Alternatives Considered

- **Separate decision and delivery enums.** Rejected: two fields invite contradictions.
- **Infer completion from changed code.** Rejected: touching an owner proves no requirement met.
- **Keep every implemented RFC forever.** Rejected: the records outnumber the live docs.
- **Accept an edit to an implemented RFC whose record is updated to match.** Rejected:
  enforcement becomes a formality.
- **A hash of the RFC stored in it.** Rejected: the author can recompute it, and two seals that
  can disagree need a rule for which wins.
- **Seal in CI after merge.** Rejected: an unreviewed bot commit that needs write access and
  works on GitHub only.
- **Freeze implemented RFCs against renames, ignore their link targets, or exempt them from
  `links`.** Rejected: the first freezes every doc an old RFC linked, the second lets a sealed
  record change what it cites, and a broken link is broken for the reader whatever the state.
- **Numbers or creation dates.** Rejected: a number catches a collision only after both branches
  merged, the date a branch started a record is not when it landed, and no command needs the
  order.
- **A command that prints an RFC's owner's part:** reading the top of the file does the same.
- **A file per part of an RFC:** the two would drift apart.
- **A word limit on the owner's part:** a long problem can be the right length; density is what
  hurts scanning.
- **Three weights:** a medium would share the large shape, adding a label but no rule.
- **Name the RFC in the diff run, such as a `--rfc` flag.** Rejected: `change verify <rfc>`
  already takes it, and a second route would be a second implementation of one rule.
- **Keep the scope warning and let a commit trailer answer it.** Rejected: the trailer would
  record that a change was outside an RFC it was never for.

## Consequences

- Stale lifecycle metadata surfaces, because an RFC's state can be contradicted mechanically.
- Immutability holds where a base exists, such as a `--diff` run in a pull request; a plain
  `check` does not notice an edit to an implemented RFC. A consolidation or wipe is merged past
  the failing seals, or happens in a new history.
- A rename and the retargets it needs land in one change; split in two, each half fails.
- Long titles make long filenames.
- An owner can stop after an RFC's Summary when it says nothing waits for them.
- The density hint will sometimes fire on a paragraph that needs its names; an ignore comment
  with a reason answers it.
- No check can tell whether a decision was buried in the agent's part; review still has to.
- The second reset left the published 0.4.0 outside `main`'s history, so it was withdrawn and
  0.4.1 released from the new one, and every clone re-clones.
- A `--diff` run on a branch with an accepted RFC is no longer warned about components that RFC
  does not declare, and nothing now reports an accepted RFC whose components the diff does not
  touch.
- A change outside any RFC's scope is caught only when someone runs the change commands for an
  RFC; `uniqueness` still reports changed source that no doc owns.
- `change-binding` no longer reads the diff range, so it no longer reads commit history and a
  shallow clone no longer counts against it in `history-depth`.

## Changes

- 2026-10-28: Accepted [An RFC has an owner's part and an agent's part](../rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md):
  every RFC declares a weight and opens with an owner's part, which `rfc-structure` checks.
- 2026-10-29: `check --diff` stopped comparing a change with every accepted RFC's `affects`;
  `change verify` and `change finalize` judge scope against the one RFC they are given.
- 2026-10-29: Accepted [Decision records govern what they decide](../rfcs/decision-records-govern-what-they-decide.md).
- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  a trailer answers removing an implemented RFC, and tasks carry checkboxes.
