---
id: finding-classes-decide-what-blocks
title: Finding classes decide what blocks
status: stable
describes: []
summary: Every check is deterministic and every finding code is certain, hint or time; certain findings block unless a draft excuses one as unfinished, hints are investigated, and time findings stay off a diff.
governs:
  - src/irminsul/checks/base.py
  - src/irminsul/checks/pipeline.py#class_of
  - src/irminsul/checks/pipeline.py#effective_class
  - src/irminsul/checks/pipeline.py#apply_classes
  - src/irminsul/checks/pipeline.py#failing_findings
  - src/irminsul/checks/pipeline.py#_drafts_exempt
  - src/irminsul/checks/pipeline.py#_on_draft
  - src/irminsul/checks/pipeline.py#answer_of
  - src/irminsul/checks/pipeline.py#_with_answer
  - src/irminsul/checks/ignore_comments.py
  - src/irminsul/fix.py
  - src/irminsul/source_tree.py
  - src/irminsul/checks/dependency_check.py
  - "!src/irminsul/checks/dependency_check.py#IMPORT_LANGUAGE"
  - src/irminsul/checks/new_dependency.py
  - src/irminsul/cli.py#_failing_classes
  - src/irminsul/cli.py#explain_command
  - checks.enabled
  - src/irminsul/checks/mtime_drift.py
  - overrides.mtime_drift_days
  - paths.source_roots
  - paths.source_includes
  - paths.source_excludes
  - paths.honor_gitignore
retires:
  - id: split-check-lists
    kind: concept
    matches:
      - soft_deterministic
      - checks.hard
      - HARD_REGISTRY
      - SOFT_REGISTRY
      - hard check
      - hard checks
      - soft check
      - soft checks
      - soft deterministic
    guidance: List the checks to run in `checks.enabled`; whether a finding blocks follows its class, certain, hint, or time.
  - id: hard-and-configured-profiles
    kind: concept
    matches:
      - --profile=hard
      - --profile hard
      - --profile=configured
      - --profile configured
      - "profile: hard"
      - "profile: configured"
      - hard profile
      - configured profile
    guidance: Run `irminsul check`, which runs the enabled checks; `--only <check>` runs any registered check, enabled or not.
  - id: co-change-acknowledgement-codes
    kind: concept
    matches:
      - co-change/acknowledged
      - co-change/invalid-acknowledgement
      - co-change/unused-acknowledgement
    guidance: An accepted finding keeps its own code at info; misuse is `acknowledgement/invalid` or `acknowledgement/unused`.
---

# Finding classes decide what blocks

## Status

Accepted, 2026-10-28.

## Context

A check that passes and fails on the same tree cannot gate a merge, and one that depends on a
model's judgment cannot be argued with. Deterministic checks still report two kinds of thing:
proof that the tree breaks a rule, and a suspicion a reader has to judge. One check emits both:
`claim-anchor` reports a symbol that does not exist, and code that changed since a claim was
pinned. Blocking a merge on a suspicion leaves an agent two ways to get green: game the signal,
such as touching a doc to reset its age, or suppress it. A draft really is unfinished, but a
status that excused every error would make one word of frontmatter the cheapest green run.

## Decision

- **Deterministic only.** Checks are graph operations, regular expressions, glob resolution,
  syntax-tree reads and git arithmetic. No check calls a model; `external-links` alone touches
  the network.
- **Every finding code has a [class](../GLOSSARY.md#finding-class)**, declared in its check's
  `classes` beside its explanation. A test requires one for every explained code, and
  `irminsul explain <code>` prints it; this record keeps no table, which would drift.
  - **Certain:** the tree provably breaks a rule. An error, which fails every run unless a
    baseline or `--delta` filters it out.
  - **Hint:** deciding needs judgment. A warning, which fails a run only under
    `--fail-on hint`, or an info, which never does. It is answered by fixing the doc, a
    reasoned ignore comment, or an acknowledgement
    ([A change is judged from its merge base to the working tree](a-change-is-judged-from-its-merge-base-to-the-working-tree.md)).
  - **Time:** caused by elapsed time or the outside world. A warning, which fails only under
    `--fail-on time`, or an info. A run given a diff range leaves it out, so a pull request is
    never blamed for the calendar.
- **A draft excuses an unfinished doc, not a wrong one.** A check declares `drafts_exempt`, the
  certain codes that report a doc as unfinished, such as a missing `summary:`. On a `draft`
  doc those are warnings that enforce as hints, so `--fail-on hint` still fails on them. Every
  other certain code is an error whatever the status.
- **One enabled list.** `checks.enabled` names the checks to run; a config with `checks.hard`
  or `checks.soft_deterministic` fails to load and names `checks.enabled`. `--only` runs any
  registered check.
- **Ignore comments reach hints and time findings only.** One naming a certain code, or a check
  whose every code is certain, is `ignore-comment/certain-finding`, and one that suppresses
  nothing is `ignore-comment/unused`, also certain. No check keeps a suppression grammar of its
  own.
- **JSON gives each finding its `class` and the `effective_class` it enforces as.**
- **Contradiction, not completeness, where the code knows.** `import-deps` reports a
  `depends_on` entry no import backs; a missing one is reported only for an import edge a
  change adds, as the hint `new-dependency`.
- **Fixes remediate, never guess.** A check fixes only findings it emits, and a fix that
  rewrites load-bearing content waits for `--confirm`.
- **One source policy.** Every check, report and surface reads one inventory: the configured
  roots, the repository's `.gitignore` when `paths.honor_gitignore` is on, explicit includes
  and excludes, and symlinks contained to their root.
- **Every finding code declares one answer.** Beside its class,
  each code a check explains, info and time codes included, declares `fix`, `line` (an ignore
  comment on its line), `pin` (a re-pin until the content moves) or `trailer` (an
  `Irminsul-Reviewed` commit trailer, the sign-off for one change), and `irminsul explain`
  prints it. A test fails on a code with no answer, and a runtime guard on a `line` code
  reported without a line or a `trailer` code reported without a subject. No new waiver is
  added.
- **Each code takes only its declared answer** (accepted, not yet implemented). An ignore
  comment waives only a code declared `line`; one naming any other hint or time code is
  `ignore-comment/wrong-answer`, certain. A standalone comment directly above a fenced block, or
  an `ignore-start` and `ignore-end` pair around it, covers the fenced lines.
- **Draft leniency lives in `drafts_exempt` alone** (accepted, not yet implemented). Failing on
  hints does not fail on a certain finding the draft exemption demoted, which fails again once
  the doc is stable. `certain_severity` goes, `phantom-layer/hollow-layer` joins the exemption in
  place of `layer-under-construction`, and the draft skip in `code-references` becomes a
  declaration the pipeline applies. This replaces "`--fail-on hint` still fails on them" above.
- **`mtime-drift` is deleted** (accepted, not yet implemented), with
  `overrides.mtime_drift_days`: `co-change`, pins and `list review --changed` already ask about
  a doc whose source changed, and its tombstone joins this record in the change that removes
  the check.
- **Two certain codes that judge meaning become hints declared `line`** (accepted, not yet
  implemented): `schema-leak/pattern-match`, and a bare flag no program precedes, which
  [Derive facts and leave meaning to the reader](derive-facts-and-leave-meaning-to-the-reader.md)
  splits out of `inventory-drift/unknown-mention`. `import-deps/hallucinated-dependency` also
  reads a literal `importlib.import_module` call.

## Alternatives Considered

- **An LLM-backed advisory check.** Rejected: build correctness must not depend on model
  judgment; the [review queue](derive-facts-and-leave-meaning-to-the-reader.md) asks a reader.
- **Hard and soft check lists, or a class per check.** Rejected: one check emits both proven
  and suspected findings.
- **Block new hints with `--delta`.** Rejected: a hint on a correct doc has no honest fix.
- **Promote rot hints to errors in the components layer.** Rejected: a layer does not make a
  suspicion a proof.
- **Demote every certain finding on a draft, or only on a doc new since the merge base.**
  Rejected: the first makes the status a control on the gate; the second needs a diff, so a
  plain run falls back to the first.
- **No demotion.** Rejected: a fresh scaffold would fail until finished.
- **`git ls-files` or `git check-ignore` for the inventory.** Rejected: source roots may sit
  outside git, and global excludes make results machine-dependent.

## Consequences

- The same tree always yields the same findings, so CI can gate merges; what only reading can
  decide is left to the review queue.
- Adding a code means choosing its class and whether it reports a doc as unfinished. A code
  whose certainty is unclear is a hint until a mechanical proof exists.
- Nothing reports a stable doc becoming a draft, or how long one has been one.

## Changes

- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md).
- 2026-10-30: The answer bullet is implemented, and the three co-change acknowledgement codes retire to `acknowledgement/*`.
