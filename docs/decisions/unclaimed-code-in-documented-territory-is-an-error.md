---
id: unclaimed-code-in-documented-territory-is-an-error
title: "Unclaimed code in documented territory is an error"
status: stable
describes: []
summary: A source file that no doc claims, in a directory that holds documented code or was added inside one, fails the build instead of warning, so documentation cannot quietly stop covering the code it covers.
---

# Unclaimed code in documented territory is an error

## Status

Accepted, 2026-09-15. Changes the class `uniqueness/undocumented-file` was given in
[Finding classes decide what blocks](finding-classes-decide-what-blocks.md), whose
table still records it as a hint.

## Context

Every check verified that what a doc says is true. Nothing verified that a doc still says
anything. The cheapest way to satisfy almost any finding was therefore to delete the
sentence that caused it, and the cheapest way to add undocumented code was to add it: a
source file no `describes` glob claimed produced `uniqueness/undocumented-file`, a hint,
which does not fail a run.

Two holes compounded. A new directory escaped entirely — the rule asked whether the file's
own directory already held claimed code, so adding `src/pkg/newthing/mod.py` put it under
no covered directory of its own however well documented `src/pkg` was. And narrowing a
`describes` glob from `src/pkg/**` to one file moved dozens of files into the same silent
category, at the cost of one line and no error.

The hint class was chosen to make adoption possible: a brownfield repository has
undocumented code everywhere, and failing its build on day one would stop anyone adopting.
That reasoning was sound, but the baseline was built for exactly this and records certain
findings only, so the hint class was doing the baseline's job.

## Decision

- **A source file in documented territory that no doc claims is a certain finding.** It
  fails the build like any other certain finding, and `irminsul check --init-baseline`
  records the existing ones so an adopting repository starts green and cannot grow the
  set.
- **Territory is a directory that holds claimed code, or one added inside such a
  directory.** A sibling tree nobody has begun documenting is still not territory, so a
  brownfield repository can be adopted one directory at a time; but a new subdirectory of
  documented code inherits the obligation rather than escaping it by being new.
- **The finding names the command that answers it.** `irminsul context <path>` reports the
  nearest owning doc, so the remedy is to extend that doc rather than to guess.

## Alternatives Considered

- **Leave it a hint and rely on `--strict`.** Rejected: the workflows `irminsul init`
  scaffolds do not pass `--strict`, and the agent protocol tells an agent that plain
  `irminsul check` exiting 0 means the change is done.
- **Treat every directory under a source root as territory.** Rejected: one claimed file
  anywhere would make the whole root territory, which floods a brownfield repository and
  makes `list undocumented --all` redundant.
- **Require a claim per public symbol rather than per file.** Rejected for now: it is a
  much larger obligation, and the per-file rule is the floor this decision is about.

## Consequences

- An existing repository that has been running with unclaimed files sees them as errors on
  the first run after upgrading. `check --init-baseline` is the intended answer, and the
  baseline can only shrink afterwards.
- Adding a directory of code now requires saying which doc describes it, in the same change.
- `list undocumented` selects the finding by code rather than by severity, since severity is
  no longer what distinguishes it.
