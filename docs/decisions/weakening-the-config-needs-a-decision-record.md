---
id: weakening-the-config-needs-a-decision-record
title: "Weakening the config needs a decision record"
status: stable
describes: []
summary: Under --diff, turning a check or a layer rule off is certain unless the same change adds a decision record naming it; narrowing what the checks read is a hint.
---

# Weakening the config needs a decision record

## Status

Accepted, 2026-09-15.

## Context

A change is judged by the config at its head. An agent stuck on a failing check can
delete the check from `checks.enabled`, or set `require_tests = false`, and the same run
that should stop it passes. A person may ask for exactly that, so blocking every removal
would be wrong, but the removal must be visible to whoever reviews the change. Code
owners on the config file do not help: an agent working with its user's credentials can
approve its own pull request.

## Decision

- **Under `--diff`, `diff-integrity` compares `irminsul.toml` with the merge base.**
- **A check removed from `checks.enabled` is certain** (`diff-integrity/check-disabled`),
  and so is a layer rule turned off (`diff-integrity/layer-rule-disabled`).
- **A decision record the same diff adds, naming the check or rule in a code span,
  clears it.** Loosening the gate then leaves a written reason in the decisions layer,
  which the reviewer reads and later changes inherit. Editing an existing record does not
  count, because a check name such as `links` is an ordinary word an old record may
  already contain.
- **Narrowing what checks read is a hint**: an added source exclude or include, a removed
  source root or language, or gitignore turned on (`diff-integrity/source-excluded`), and
  a file removed from `paths.extra_docs` (`diff-integrity/extra-doc-removed`), because
  these are routine and their effect depends on the files involved.
- **The base config decides what is sealed.** The decisions and RFC folders and the
  baseline path come from the config at the merge base, so a change cannot move them.
  A base with no config is an adoption and has nothing to weaken.

## Alternatives Considered

- **Code owners on the config.** Rejected: the approval can come from the agent itself.
- **Always block a removal.** Rejected: a person deciding to drop a check needs a path
  that does not involve bypassing the gate.

## Consequences

- Naming the setting in a decision record is a mechanical test; whether the reason is
  good is left to the reviewer.
- A local `irminsul check` without `--diff` does not compare the config.
