---
id: baseline
title: Baseline ratchet
status: stable
summary: Records existing certain findings so CI fails only on new ones; it shrinks, and grows only by decision.
depends_on:
  - checks
  - file-writing
  - user-errors
describes:
  - src/irminsul/baseline.py
  - src/irminsul/delta.py
owns_tests:
  - tests/test_baseline.py
  - tests/test_cli_check_baseline.py
  - tests/test_cli_check_delta.py
  - tests/test_delta.py
  - tests/test_delta_identity.py
claims:
  - id: baseline-only-shrinks
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: "A baseline records only certain findings, and no command adds an entry to one that exists: creation refuses to overwrite it, and an update may only remove entries. Under `--diff`, a change that gives it more entries fails unless a trailer names the baseline file or the change is the one that adopts Irminsul."
    evidence:
      - src/irminsul/baseline.py
      - src/irminsul/checks/diff_integrity.py
    pinned:
      src/irminsul/baseline.py: sha256:250bd0a339a1
      src/irminsul/checks/diff_integrity.py: sha256:190f2511cbbb
---

# Baseline ratchet

Without a baseline, adopting Irminsul on an existing codebase would be all-or-nothing: every pre-existing violation would have to be fixed before CI could go green. The baseline is the escape hatch that does not become a loophole ([A baseline holds certain findings and grows only by decision](../decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md)): `irminsul baseline init` records the current certain findings in `paths.baseline`, and [`check`](cli.md) hides exactly those, so anything new still fails the build.

## How matching works

A baselined finding is identified by the fingerprint of its check name, repo-relative path and message. The line number is deliberately left out, so a finding that merely moves within a file stays hidden, while one whose message changes counts as new. That is safe because a certain finding's message names the item it is about, such as a broken link's target, so one entry cannot hide a different problem in the same doc; a test runs every check over the fixture corpus and fails when two certain findings in one doc share a message on different lines.

What may be recorded is `baselinable` in `src/irminsul/baseline.py`: a certain finding from a registered check whose code audits no suppression (`may_be_debt`). The writer, the filter and `--delta` all ask it, so a baseline can hide neither its own growth nor an obsolete exception, such as an unused ignore comment or an [adoption record](adoption-record.md) that does not hold up.

## The ratchet

No command adds an entry to an existing baseline — `baseline init` refuses when one exists and `baseline update` only removes the entries that match nothing — and under `--diff` a change that gives the file more entries fails with `diff-integrity/baseline-grew` unless a trailer names the file or the change is the one that adopts Irminsul. <!-- claim:baseline-only-shrinks -->

The trailer is for an upgrade whose new rules find problems in old docs: its pull request re-creates the baseline and carries the trailer instead of stalling until every one is fixed ([A baseline holds certain findings and grows only by decision](../decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md)). The change that adopts Irminsul is the one exception: its merge base holds neither a config nor a baseline, so there is no ratchet yet and the first baseline is a creation. Without that, the pull request workflow [`init`](init.md) scaffolds would fail the very change that adds it.

What the baseline hides stays visible: each run counts the hidden findings and the fixed entries, `--format github` adds a warning annotation and, when `GITHUB_STEP_SUMMARY` is set, lists every hidden finding in the job summary, `irminsul list baseline` marks each entry `hidden` or `fixed`, and `--no-baseline` shows the full picture.

## Delta mode (`check --delta`)

Where the baseline grandfathers a repository's whole backlog once, `--delta` answers a narrower question per run: which findings did *this* working tree introduce? `run_delta` in `checks/pipeline.py` makes the same run at `--delta-base` in a scratch `git worktree` and reports only findings the base run did not have, by the baseline's own fingerprint and `may_be_debt`, so "new" means the same thing under both, and [`context --after-edit`](context.md) measures what a change introduced with it too.

When the base names the same tree as the working tree, every finding would be pre-existing and the run would exit 0 having checked nothing, so it exits 2. `--delta` is not the gate; plain `irminsul check` is, and `check --diff HEAD` judges the same edits as a change ([A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md)).

`--delta` refuses, with exit 2, any configured tree that answers to another git repository: the `siblings` layout's code repository ([private docs](../guides/private-docs.md)), or a docs root that is a submodule. `git worktree add` checks out tracked files only, so the base would hold none of that tree and every finding over it would come back as new. Comparing across that boundary is refused rather than attempted, because one `--delta-base` cannot name a point in a second repository's history: run `check` without `--delta` there, and read `mtime-drift` as the cross-repository signal.

## Scope & Limitations

The baseline applies to whichever checks were run when it was written and when it is applied; it stores findings, not the selection. It suppresses findings, not checks — a baselined check keeps running and keeps catching regressions elsewhere. A greenfield repo should never need one: this repo's own tree has no baseline file, and scaffolded repos do not get one.
