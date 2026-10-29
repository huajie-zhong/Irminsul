---
id: a-path-is-named-when-git-lists-it
title: "A path is named when git lists it"
status: stable
describes: []
rfc_state: accepted
affects:
  - checks
resolved_by: docs/decisions/code-is-named-in-code-spans-and-bound-by-anchors.md
summary: A path a doc names exists when git lists it or the source walk holds it, not when a file happens to be on one machine's disk, so the same tree gives the same findings everywhere.
required_updates: []
weight: small
---

# A path is named when git lists it

## Summary

A path a doc names counts as existing when git lists it, or when the declared source walk
holds it, not when a file merely happens to be on your disk. Today a gitignored generated
file, such as an `openapi.json` a build writes, passes on your machine and fails in CI, and an
ignore comment answering it flips between "used" and "unused". You sign off on the rule, and
on correcting the code-span record's sentence that counted any file on disk. One decision,
answered.

## Decisions

Answered by the owner on 2026-10-29:

1. **The git rule**, as a small RFC implemented after decision records become living topics,
   so the correction to the code-span record is an edit in place with a trailer and a dated
   Changes line.

## Design detail

- **The rule.** In a git repository, a named path exists when `git ls-files --cached --others
  --exclude-standard` lists it, so a new file the change adds counts and a gitignored one does
  not, or when the configured source walk holds it. A path naming a directory exists when git
  lists a file under it. Outside a git repository, such as an extracted tarball, the disk
  answers, which is still the same answer for every reader of that tree.
- **Where it applies.** `code-references` (`unknown-path`, and the `FileIndex` that decides
  what a code span names, whose disk probes and lazy walk go) and `claim-provenance`
  (`evidence-path-missing`, through `resolve_display_path` in `checks/globs.py`, which calls
  `.exists()` today). One listing per repository serves both: a sibling source repository is
  listed in its own repository. `resolve_display_path` also serves `checks/globs.py` itself and
  `_evidence_exists` in `checks/diff_integrity.py`, which asks whether a removed claim's
  evidence survives, so both follow the same listing. Other probes of the disk for a path a doc
  names, behind `links/broken-link`, `coverage/tests-path-missing` and
  `claim-anchor/missing-file`, are outside this RFC.
- **The record it corrects.** `code-is-named-in-code-spans-and-bound-by-anchors` says a path is
  named when it is "a file on disk outside `.git` and dependency directories". That clause
  becomes "a file git lists, or one the source walk holds". The test
  `test_a_file_git_ignores_is_named_when_it_is_on_disk` pins the old clause and is replaced.
- **Evidence.** The bug-fix lane reproduced the flip (`gen/openapi.json`, gitignored, on disk:
  silent locally, both codes in a fresh clone) and prototyped the `code-references` half; only
  the pinned test failed and this repository stayed green.
- **Cost.** A doc that names a gitignored generated file is reported everywhere, as it already
  is in CI; it names the generator or the committed schema instead, or keeps the mention with
  an ignore comment that now behaves the same on every machine.

## Requirements

### Requirement: A named path exists when git lists it
ID: a-named-path-exists-when-git-lists-it
Provenance: code

In a git repository, `code-references` and `claim-provenance` SHALL treat a named path as
existing only when git lists it as tracked or as untracked and not ignored, or when the
configured source walk holds it, and SHALL NOT treat a file as existing because it is on disk.

#### Scenario: A gitignored generated file
- **WHEN** a doc names `gen/openapi.json` in a code span, the file is on disk, and `.gitignore` lists `gen/`
- **THEN** the run reports `code-references/unknown-path`, as a fresh clone does

#### Scenario: A new file the change adds
- **WHEN** a doc names `src/new_module.py`, created in the working tree and not yet committed
- **THEN** the run reports no `code-references/unknown-path` for it

### Requirement: A directory is named when git lists a file under it
ID: a-directory-is-named-when-git-lists-a-file-under-it
Provenance: code

A named path that is a directory SHALL exist when git lists at least one file under it.

#### Scenario: A directory of tracked files
- **WHEN** a claim's evidence names `src/irminsul/change` and git lists files under it
- **THEN** the run reports no `claim-provenance/evidence-path-missing` for it

### Requirement: Without git the disk answers
ID: without-git-the-disk-answers
Provenance: code

Outside a git repository, a named path SHALL exist when it is on disk.

#### Scenario: An extracted tarball
- **WHEN** the tree has no `.git` and a doc names a file that is on disk
- **THEN** the run reports no `code-references/unknown-path` for it

## Tasks

- `T1` Build one git listing per repository and decide `code-references` paths from it. (req: a-named-path-exists-when-git-lists-it)
- `T2` Decide `claim-provenance` evidence paths from the same listing. (req: a-named-path-exists-when-git-lists-it)
- `T3` Count a directory when git lists a file under it. (req: a-directory-is-named-when-git-lists-a-file-under-it)
- `T4` Fall back to the disk outside a git repository. (req: without-git-the-disk-answers)

## Resolution

Accepted by the owner on 2026-10-29, with the answer recorded under Decisions, and resolved by
[Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md), which states the rule as accepted and not yet implemented beside the clause it replaces,
with a dated item under its Changes. It was accepted at the second history reset, so the
correction is an edit of that record in place rather than a new record.
