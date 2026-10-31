---
id: change
title: Change lifecycle
status: stable
summary: Bound-change lifecycle reports and transitions for RFCs.
depends_on:
  - baseline
  - checks
  - config
  - docgraph
  - frontmatter
  - git
  - user-errors
describes:
  - src/irminsul/change/**
owns_tests:
  - tests/test_change_finalize.py
  - tests/test_change_footprint.py
  - tests/test_change_report.py
  - tests/test_change_transition.py
  - tests/test_cli_change.py
  - tests/test_requirements_parser.py
  - tests/test_tasks_parser.py
claims:
  - id: transition-applies-human-decisions
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: change transition writes only the two states a human decides, accepted and rejected; implemented is written exclusively by change finalize.
    evidence:
      - src/irminsul/change/transition.py
      - src/irminsul/change/finalize.py
    pinned:
      src/irminsul/change/transition.py: sha256:ee4464bfd577
      src/irminsul/change/finalize.py: sha256:d1c2e789012e
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - change status
      - change verify
      - change transition
---

# Change lifecycle

The `irminsul change` command group treats an RFC as the forward artifact for significant change ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): a work item that moves through `draft -> accepted -> implemented`, with `rejected` as the alternate terminal state. The module owns the read-only reports and the confirmed transitions; the RFC document itself stays the single authored source of intent.

Two linked rules shape every report:

1. **Derive what is mechanically knowable.** Changed files, owning components, test evidence, and check findings come from the diff and the [DocGraph](docgraph.md) on every call; they are never copied onto the RFC.
2. **Expose evidence for semantic judgment.** Whether an implementation satisfies its intent is not derivable. Reports separate mechanical *blockers*, derived *evidence*, and *semantic-review clues* — and may say `mechanically_ready_for`, never "behavior is correct".

## Transitions

`change status` and `change verify` are the read-only reports. `change transition` writes only the two states a person decides, `accepted` and `rejected`, and `implemented` is written only by `change finalize`. <!-- claim:transition-applies-human-decisions --> Each applies its coupled edits in one confirmed pass (an acceptance also records the decision record `--resolved-by` names), and without `--confirm` prints the plan and writes nothing.

`change finalize` refuses a working tree with uncommitted work, with or without `--confirm`, before it plans anything, because a change with uncommitted work in it names a change that does not exist yet. `refuse_uncommitted_work` in `src/irminsul/change/finalize.py` is that refusal, so planning stays a pure function of the tree it is given. Which symbol satisfies a requirement is a semantic judgment code cannot infer, so each `--anchor <req>=<path>#<symbol>` binding is explicit, confirmed input, and an owner the most-specific-claim rule leaves ambiguous needs `--owner <req>=<component>`. When the components that claim a requirement's bindings are not among the RFC's `affects`, the `ambiguous-owner` blocker names them and says `affects` does not declare them, and its suggestion lists the declared components to choose from. Promotion is idempotent: a claim id already present in the owner doc is skipped, but the `implements` backlink is still ensured, so a hand-migrated claim never leaves the RFC without its inbound edge, and re-running against an identical implemented RFC writes nothing. The resulting anchor is a freshness tripwire, not proof of behavior.

Once the protected branch records an RFC as implemented, `diff-integrity` reports an edit to it under `--diff` ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)), so a later extension starts a new RFC.

## Requirements and tasks

A behavior-changing RFC carries a `## Requirements` section of blocks with a stable id, a `Provenance: code|adr|citation` obligation, SHALL/MUST text and WHEN/THEN scenarios; a maintenance RFC writes the explicit sentence `No new behavioral requirements: ...` instead, which is reviewable intent rather than a silent omission. Reports address each requirement as `<rfc-id>#<requirement-id>`, and a `Provenance: code` requirement stays an unbound evidence obligation until finalization binds it to an anchored claim. Grammar findings are warnings while drafting and blockers at `change transition ... accepted`.

`## Tasks` is a static plan: items with stable ids that reference a requirement or a declared component, never assignees, deadlines or status. The reports list the tasks by id and text, and the evidence is the RFC's, listed once: the changed source of the components the change touches and the changed files their `recommended_tests:` name. Evidence is not per task, because a task may name no file of its own, so every task would show the same files. One clue for the whole RFC says what the change shows: no changed source belongs to its components, changed source with no changed test, or, when both changed, a request to confirm the changed tests assert each task's scenario. A changed test is the weakest evidence: Irminsul runs nothing, so it says a recommended test file was edited, never that it ran, passed, or covers the task beside it. When no baseline resolves, the evidence reads `unknown`, and the JSON carries `evidence_measured: false` beside its empty evidence list: an unmeasured change must never read as an unchanged one. A plan that fails to parse is a finding, never a silent `0/0`.

## Mechanical readiness

Readiness is composition, not a new invariant ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)). Each rule is one predicate in `src/irminsul/change/gate.py`, which the check owning the rule calls with the RFC's own state and `gate` calls with the state it judges, so a blocker and the finding for one rule share a wording and a code. `change verify`, `change finalize` and `change transition` ask the same `gate` for their target, so verify cannot report ready for a tree finalization would refuse; `change status` asks `step_gate`, which blocks on exactly what the RFC's next step does.

Scope is the one rule no check owns. `_scope` in `src/irminsul/change/gate.py` compares the components the change touched with the `affects` of the one RFC the command was given, so finalization, and `change verify` of an accepted RFC, block on source in a component `affects` leaves out (`unreconciled-scope`) and on source no component claims (`unowned-change`). `check --diff` makes no such comparison, because it cannot know which RFC a change is for ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)).

Findings are partitioned by their relation to the change, and nothing is dropped in between. Every error an enabled check reports after the baseline is a blocker, because it would fail `irminsul check` too; every warning is either scoped to this change — the RFC, a declared component doc, or a changed path — or counted under `repository_debt`, visible but never a barrier to someone else's transition.
<!-- anchor: src/irminsul/change/report.py#ChangeReport.repository_debt @sha256:732e1616b7ff -->

## Diff baseline

Evidence is measured over the range `check --diff` judges, from the merge base to the working tree, or to `HEAD` under `--committed-only` ([A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md)), and the resolver never guesses a clean result: a base it cannot resolve is `unknown`, which is never mechanically ready for finalization.

A deleted path is matched against the same configured source policy as the on-disk inventory. A deletion that `.gitignore` or `paths.source_excludes` covers therefore does not appear as owned or undocumented source merely because the file is no longer there for the walker.

## Scope & Limitations

The module does not implement tasks, judge semantic completion, or transition an RFC on its own conclusions — acceptance and rejection are human decisions it validates and records.
