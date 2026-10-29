---
id: a-history-file-is-checked-for-its-links
title: "A history file is checked for its links"
status: stable
describes: []
rfc_state: accepted
affects:
  - checks
  - config
  - docgraph
  - refs
resolved_by: docs/decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md
summary: A file that records history, such as a changelog, is named under `paths.history_docs` and checked for its links alone, so folding a decision record or an RFC no longer breaks a changelog link unseen.
required_updates: []
weight: large
---

# A history file is checked for its links

## Summary

A changelog's links to decision records and [RFCs](../GLOSSARY.md#rfc) are checked, so removing or folding one
can no longer leave the changelog pointing at nothing. A new setting names the history
files, the changelog by default, and they are checked for their links and nothing else.
An adopter whose changelog already has a broken local link fails on upgrade until it is
repaired. One decision, answered.

## Problem

The changelog links to the records each release changed. At the second history reset four
decision records were folded into others and deleted, and two of the changelog's links
pointed at them. No check reads the changelog, so nothing reported them; they were found
by searching the tree and retargeted by hand.

Reading it as **guidance**, the root files such as the README that the checks read
alongside the docs, would be wrong. A changelog names removed commands and code on purpose,
and on this repository the guidance checks report 39 of those mentions as errors and
warnings.

## How it works

A second list in the config names history files. They are read once, by the same reader as
guidance, and only two things use them: the link check, which reports a link to a file or
heading that does not exist, and the backlink query, which lists them among the files that
link to a doc. The checks that judge whether prose matches today's code skip them. Dropping
a file from the list is sealed in a pull request, as dropping a guidance file is.

## Cost and risk

A setting, a seal entry, and a flag on the files the guidance reader returns. An adopter
whose changelog has a broken local link gets a certain finding on upgrade; repairing the
link answers it, and so does setting the list to empty. Links to issues and pull requests
are web addresses, which the link check does not judge, so most changelogs are unaffected.

## Decisions

Answered by the owner on 2026-10-29:

1. **A links-only list of history files, defaulting to the changelog**, rather than reading
   the changelog as guidance and linking each removed name to its record, or leaving it
   unchecked.

## Design detail

- **The setting.** `paths.history_docs`, a list of repo-relative Markdown files, default
  `["CHANGELOG.md"]`. A listed file that does not exist is skipped, as one under
  `paths.extra_docs` is. A file named by both lists is a config error, because the two are
  judged differently.
- **One reader.** `read_guidance` in `src/irminsul/docgraph.py` also reads the history
  files, and each `GuidanceFile` says whether it is history, so links and headings parse
  once. The guidance checks iterate guidance files only.
- **What reads them.** `links` (`broken-link`, `unknown-anchor`, through
  `_guidance_file_findings`) and `refs`, whose weak hits include guidance files once the fix
  on branch `fix/dogfood-notes` lands. Not `code-references`, `retired-references`,
  `glossary-discipline`, the ignore-comment pass, or `list review`: a history file describes
  a past release, not the code.
- **The seal.** `diff-integrity` seals `paths.extra_docs` against narrowing with
  `diff-integrity/extra-doc-removed`; `paths.history_docs` gets the same entry in the config
  seal table, and the code's message names the list the file left.
- **Governing record.** `docs-are-atoms-in-six-layers-and-code-has-one-owner` governs
  `paths.docs_root`; its `governs:` gains `paths.extra_docs` and `paths.history_docs`, and its
  Decision states which files are read and how. The seal is stated in
  `a-change-may-not-lower-its-own-gates`, which governs the `diff-integrity` seal code.
- **Evidence.** Naming `CHANGELOG.md` under `paths.extra_docs` on main 6cb5c1e raised 26
  `retired-references/retired-reference`, 12 `code-references/unknown-path` and 1
  `code-references/unknown-command`, and no `links` finding, so this repository lands green.
- **Backlog.** Closes the changelog half of `docstrings-and-changelog-links-unchecked`.
- **Not chosen.** A history file read by every check with the history-shaped findings
  suppressed: a second rule inside each check for one kind of file.

## Requirements

### Requirement: A history file's links are checked
ID: history-file-links-checked
Provenance: code

`links` SHALL report a local link to a missing file, and a link to a missing heading, in
each file `paths.history_docs` names, as it does in a guidance file.

#### Scenario: A changelog links a removed record
- **WHEN** `CHANGELOG.md` links `docs/decisions/gone.md` and that file does not exist
- **THEN** the run reports `links/broken-link` at that line of `CHANGELOG.md`

#### Scenario: The default needs no setting
- **WHEN** `irminsul.toml` does not set `paths.history_docs` and `CHANGELOG.md` exists
- **THEN** `links` reads `CHANGELOG.md`

### Requirement: A history file is read for its links alone
ID: history-file-read-for-links-alone
Provenance: code

`code-references`, `retired-references`, `glossary-discipline`, the ignore-comment pass and
`list review` SHALL NOT read a file that `paths.history_docs` names.

#### Scenario: A changelog names a retired command
- **WHEN** `CHANGELOG.md` says a release removed `list orphans`, and a decision record retires `list orphans`
- **THEN** the run reports no `retired-references/retired-reference` for `CHANGELOG.md`

### Requirement: Refs lists a history file's links
ID: refs-lists-history-file-links
Provenance: code

`irminsul refs <doc>` SHALL list each link to that doc from a file `paths.history_docs`
names among its weak hits.

#### Scenario: A changelog links a decision record
- **WHEN** `CHANGELOG.md` links `docs/decisions/a.md` and `irminsul refs a` runs
- **THEN** the weak hits include `CHANGELOG.md` at that line

### Requirement: A file is guidance or history, not both
ID: guidance-or-history-not-both
Provenance: code

Loading a config whose `paths.extra_docs` and `paths.history_docs` name one file SHALL fail
with an error naming it.

#### Scenario: The changelog in both lists
- **WHEN** both lists name `CHANGELOG.md`
- **THEN** the config fails to load and the error names `CHANGELOG.md`

### Requirement: Dropping a history file is sealed
ID: history-file-removal-sealed
Provenance: code

Under `--diff`, a change that removes a file from `paths.history_docs` SHALL be reported as
`diff-integrity/extra-doc-removed`, naming `paths.history_docs`.

#### Scenario: The changelog leaves the list
- **WHEN** the base config's `paths.history_docs` names `CHANGELOG.md` and the head's is empty
- **THEN** `check --diff` reports `diff-integrity/extra-doc-removed` naming `paths.history_docs`

## Tasks

- `T1` Add `paths.history_docs` with its default and the both-lists error. (req: guidance-or-history-not-both)
- `T2` Read history files in the guidance reader, marked, and keep the guidance checks to guidance files. (req: history-file-read-for-links-alone)
- `T3` Check history files' links in `links`. (req: history-file-links-checked)
- `T4` List history files' links in `refs`. (req: refs-lists-history-file-links)
- `T5` Seal `paths.history_docs` against narrowing. (req: history-file-removal-sealed)
- `T6` State the rules in the two governing records and update `docs/components/config.md` and `docs/components/refs.md`. (component: config)

## Resolution

Accepted by the owner on 2026-10-29, with the answer recorded under Decisions, and resolved by [Docs are atoms in six layers, and code has one owner](../decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md), whose Changes item records it. [A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md) records its part too. Each rule joins its record's Decision with the implementation, as an edit in place once decision records are living topics.
