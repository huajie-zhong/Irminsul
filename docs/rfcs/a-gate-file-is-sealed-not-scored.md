---
id: a-gate-file-is-sealed-not-scored
title: "A gate file is sealed, not scored"
status: stable
describes: []
rfc_state: implemented
weight: large
affects:
  - checks
  - init
resolved_by: docs/decisions/a-change-may-not-lower-its-own-gates.md
summary: A changed workflow or action file that mentions irminsul is a certain finding until a decision record names it, replacing gate-strength scoring and the emulation of GitHub path filters.
required_updates: []
---

# A gate file is sealed, not scored

## Summary

A change can no longer weaken its own CI gate unnoticed, however the edit is spelled. Any
change to a gate file, a workflow or action definition that mentions irminsul, is a certain
finding, which blocks, until a decision record added in the same change names the file. This
replaces the code that scored how strong each gate is and re-implemented GitHub's path
filters, and the scaffolded pull-request workflow loses its path filter. Four decisions, all
made at acceptance; none waits for the owner.

## Problem

A change edits `.github/workflows/docs-pr.yml` so the step reads
`irminsul check --diff origin/main || echo docs drift`.

1. On GitHub the check fails, `echo` succeeds, and the job passes.
2. The scorer's tail rule knows `|| true` and `|| :`, so today this passes unreported, as
   `|| exit 0` does.
3. Proposed, `diff-integrity/gate-file-changed` names the workflow, whatever the edit says.
4. The change passes once it adds a stable decision record whose `## Decision` names the
   workflow's path in a code span, where the reviewer reads why.

The scorer reads workflows for meaning: per triggering event it counts five axes of the
irminsul call, decides whether a step can fail the run, and re-implements path filters. Each
rule guesses at GitHub's semantics, each new spelling of a weakening needs a new rule, and
about 590 lines and 67 tests hold it up.

The scaffolded path filter also omits the test roots, and GitHub leaves a required check
Pending when a path filter skipped its workflow, so a pull request that touches only tests can
never merge.

## How it works

**The seal reads text, not meaning.** Weakening a gate needs an edit to a gate file, and git
reports an edit exactly, without having to know what it means. A file under
`.github/workflows/`, or named `action.yml` or `action.yaml`, is sealed when it mentions
irminsul in any case, before or after the change.

**A decision record clears one file.** It is added in the same change, is stable, and names
the file's path in a code span in its decision: the excuse the seals on settings already
accept, read by the same code.

**An adopting change is not sealed.** The seal is armed unless the base holds neither an
Irminsul config nor a baseline, the test that decides a first baseline: a change that adopts
Irminsul has nothing to weaken.

**The scaffold drops its filter**, so the gate runs on every pull request; adding one back
edits a gate file, which the seal reports.

**The earlier record is qualified, not superseded.**
[A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md)
still seals a setting that decides how much a check asks; its rule for when a CI step counts
as a gate is qualified, since a gate file is now sealed whole and no step is scored.

## Cost and risk

A harmless edit to a gate file, such as a comment or an `actions/checkout` bump, needs a
one-line decision record, and every gate file here mentions irminsul. A gate run through a
script or another repository's reusable workflow is sealed only if the calling workflow
mentions irminsul, a limit the scorer shared. The record proves a reason was written, not that
anyone agreed; branch protection is still the guard.

## Decisions

Made at acceptance, with no question left open:

1. **Seal, not score**, since the ways to discard an exit status cannot be listed for a scorer
   to learn.
2. **Certain, not a hint**: a hint does not stop the change that removes the gate, the one
   change the seal exists for.
3. **Only files that mention irminsul**: sealing every workflow would ask a lint-only edit for a
   record about a gate it does not hold.
4. **Drop the filter rather than add the test roots**: the list must track every file the gate
   reads, and one omission makes a pull request unmergeable.

## Design detail

### What is sealed

A gate file is a workflow under `.github/workflows/`, or an `action.yml` or `action.yaml`
anywhere in the repository, whose text contains `irminsul` in any case at the merge base or
at the head. Under `--diff <base>`, `diff-integrity` reports `gate-file-changed`, certain,
once for each such file the range adds, deletes, renames or edits. The seal reads text, not
YAML, so a file that stops parsing is still sealed.

It is armed unless the merge base holds neither an Irminsul config nor a baseline. A base
that dropped its config but kept its baseline has adopted, so the change that restores the
config is sealed.

### What clears it

A decision record added in the same change, with `status: stable`, whose `## Decision`
names the file's path in a code span. A deleted file is named by its base path, any other
by its head path. The setting seals that stay include `check-disabled` and
`setting-weakened`.

### What it replaces

The seal replaces the gate-strength scoring and the reimplementation of GitHub's `paths:`
filters in `src/irminsul/checks/diff_integrity.py`, with their codes `gate-weakened`,
`filter-unreadable` and `filter-not-compared`. The scorer's five axes per triggering event
were `irminsul check`, `--strict`, `--diff`, `--profile` and `--delta`.

### The scaffold

The scaffolded `docs-pr.yml` loses its `paths:` filter: both
`src/irminsul/init/workflows/*/docs-pr.yml.j2` lose `paths:`, and the template variables
only the filter read go too. The filter listed docs, config, source roots, guidance files,
the baseline, the adoption record and workflows, but not `test_roots`.

### The earlier record

[A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md)
decided that a setting deciding how much a check asks is sealed, and that a CI step counts
as a gate only if its result can fail the run. The first still holds, so the record is not
superseded, which would deprecate it whole. Its Status line gains one sentence: its two
CI-step bullets are qualified by this proposal's resolving record, because a gate file is
now sealed whole and no step is scored.

### Gate files in this repository

Every workflow here mentions `irminsul`: `ci.yml` runs it and `release.yml` names the
image. `action.yml` is the Action itself. Each change to them carries a record.

## Requirements

### Requirement: A changed gate file is certain
ID: gate-file-change-is-certain
Provenance: code

Under `--diff <base>`, when the merge base holds an Irminsul config or a baseline, `diff-integrity`
SHALL report `diff-integrity/gate-file-changed` as a certain finding for each file under
`.github/workflows/`, and each `action.yml` or `action.yaml`, that mentions `irminsul` at
the base or at the head and differs between them.

#### Scenario: Discarded exit status
- **WHEN** a change rewrites a `docs-pr.yml` step to `irminsul check --diff origin/main || echo docs drift`
- **THEN** `irminsul check --diff <base>` reports `gate-file-changed` on `.github/workflows/docs-pr.yml` and exits 1

#### Scenario: Comment-only edit
- **WHEN** a change adds only a YAML comment to a workflow that runs `irminsul check`
- **THEN** `gate-file-changed` is reported for that workflow

#### Scenario: Workflow without irminsul
- **WHEN** a change edits `.github/workflows/lint.yml`, which mentions `irminsul` on neither side
- **THEN** no `gate-file-changed` finding is reported

### Requirement: A decision record clears a named gate file
ID: decision-record-clears-gate-file
Provenance: code

A decision record added in the same change with `status: stable` whose `## Decision`
section names a gate file's path in a code span SHALL clear that file's finding, and
SHALL clear no other file's.

#### Scenario: Named file
- **WHEN** the change also adds a stable record whose `## Decision` names `.github/workflows/docs-pr.yml` in a code span
- **THEN** no `gate-file-changed` finding is reported for that file

#### Scenario: Another file named
- **WHEN** the change edits `docs-pr.yml` and `docs-nightly.yml`, and the record names only `docs-pr.yml`
- **THEN** `gate-file-changed` is reported for `docs-nightly.yml` alone

### Requirement: An adopting change is not sealed
ID: adopting-change-is-not-sealed
Provenance: code

When the merge base holds neither an Irminsul config nor a baseline, `diff-integrity`
SHALL NOT report `gate-file-changed`.

#### Scenario: First workflow
- **WHEN** a change adds `irminsul.toml` and `.github/workflows/docs-pr.yml` to a repository whose base has neither
- **THEN** no `gate-file-changed` finding is reported

#### Scenario: Config dropped, baseline kept
- **WHEN** the base holds a baseline but no `irminsul.toml`, and the change restores the config and edits `.github/workflows/docs-pr.yml`
- **THEN** `gate-file-changed` is reported for that workflow

### Requirement: Gate scoring is removed
ID: gate-scoring-removed
Provenance: code

`diff-integrity` SHALL NOT emit `gate-weakened`, `filter-unreadable` or
`filter-not-compared`, and `irminsul explain` SHALL report each as an unknown code.

#### Scenario: Old code
- **WHEN** `irminsul explain diff-integrity/gate-weakened` runs
- **THEN** it reports an unknown code

### Requirement: The scaffolded gate has no path filter
ID: scaffold-without-path-filter
Provenance: code

`irminsul init` SHALL write a `docs-pr.yml` whose `pull_request` trigger has no `paths:`
or `paths-ignore:` filter, in both repository layouts.

#### Scenario: Both layouts
- **WHEN** `irminsul init` runs, once in a same-repo layout and once with `--topology siblings`
- **THEN** neither written `docs-pr.yml` has a path filter under `pull_request`

## Tasks

- `T1` Report `gate-file-changed` for each changed gate file, and update `docs/components/checks.md` and `docs/foundation/enforcement.md`. (req: gate-file-change-is-certain)
- `T2` Clear it through the existing reader of added decision records. (req: decision-record-clears-gate-file)
- `T3` Arm the seal unless the base holds neither an Irminsul config nor a baseline. (req: adopting-change-is-not-sealed)
- `T4` Delete the scorer, the matcher and their codes; replace their tests with file-seal tests, each shown failing on a planted edit first; write the resolving record with `retires:` tombstones for the three codes and the earlier record's qualifying sentence. (req: gate-scoring-removed)
- `T5` Remove `paths:` and the variables only it read from both `docs-pr.yml.j2`, and update `docs/components/init.md`. (req: scaffold-without-path-filter)

## Resolution

Accepted 2026-10-21 and resolved by
[A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md). One change
from the first draft: the seal is armed by the test that decides a first baseline, so a
base that dropped its config but kept its baseline stays sealed.
