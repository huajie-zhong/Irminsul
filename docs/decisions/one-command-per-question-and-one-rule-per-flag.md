---
id: one-command-per-question-and-one-rule-per-flag
title: "One command per question, and one rule per flag"
status: stable
describes: []
summary: Each question has one command and each flag one meaning; maintenance writes are their own commands, a removed option names its replacement, exit 2 means the invocation was wrong and exit 1 that the command refused.
governs:
  - src/irminsul/cli.py#IrminsulGroup
  - src/irminsul/cli.py#_MOVED
  - src/irminsul/cli.py#_split_commas
  - src/irminsul/cli.py#OutputFormat
  - src/irminsul/cli.py#CheckFormat
  - src/irminsul/errors.py
  - src/irminsul/checks/pipeline.py#select_checks
  - src/irminsul/checks/pipeline.py#UnknownCheckError
retires:
  - id: status-command
    kind: cli-command
    surface_identity: status
    matches:
      - irminsul status
    guidance: Run `irminsul orient` for source ownership coverage and doc totals, and `irminsul check` for findings.
  - id: list-orphans-command
    kind: cli-command
    surface_identity: list orphans
    matches:
      - list orphans
    guidance: Run `irminsul check --only orphans`.
  - id: list-stale-command
    kind: cli-command
    surface_identity: list stale
    matches:
      - list stale
    guidance: Run `irminsul check --only stale-reaper`.
  - id: regen-command
    kind: cli-command
    surface_identity: regen agents-md
    matches:
      - regen agents-md
    guidance: Run `irminsul fix`, which rewrites the agent manifest's generated section when `agents-manifest` reports it stale.
  - id: change-graph-command
    kind: cli-command
    surface_identity: change graph
    matches:
      - change graph
    guidance: Read the RFC's own `supersedes` and `depends_on`; `irminsul check` reports one that names no doc.
  - id: change-impact-command
    kind: cli-command
    surface_identity: change impact
    matches:
      - change impact
      - change_impact
    guidance: Run `irminsul context --after-edit` for the owners and docs a change touches.
  - id: binding-readiness
    kind: concept
    matches:
      - binding_readiness
      - binding readiness
    guidance: Run `irminsul check` before `irminsul new rfc`, which scaffolds without a gate.
  - id: context-before-edit-flag
    kind: concept
    matches:
      - --before-edit
    guidance: Run `irminsul context <path...>`, which returns the packet and runs no checks.
  - id: context-changed-flag
    kind: concept
    matches:
      - context --changed
      - context_changed
    guidance: Run `irminsul context --after-edit`, or the MCP tool `context_after_edit`.
  - id: profile-flag
    kind: concept
    matches:
      - --profile
      - all-available
    guidance: List the checks to run in `checks.enabled`; `--only <check>` runs one check whether or not it is enabled.
  - id: strict-flag
    kind: concept
    matches:
      - --strict
    guidance: Pass `--fail-on hint,time`, or set the Action input `fail-on`.
  - id: check-base-and-head-ref
    kind: concept
    matches:
      - --head-ref
      - check --base-ref
      - history-depth/diff-unavailable
    guidance: Run `irminsul check --diff <base>`; `context --after-edit` and `change verify` keep `--base-ref`.
  - id: refs-symbol-flag
    kind: concept
    matches:
      - --symbol
    guidance: Search the tree for the name; `irminsul refs <doc>` lists the docs that link to a doc.
  - id: fix-check-flag
    kind: concept
    matches:
      - fix --check
    guidance: Run `irminsul fix --only <check>`.
  - id: irm-script
    kind: concept
    matches:
      - irm
    guidance: Run `irminsul`; in PowerShell `irm` is `Invoke-RestMethod`.
  - id: pre-pin-adoption-migration
    kind: concept
    matches:
      - --pin-adoption-sources
      - migrate_record
    guidance: No release wrote an adoption record without source pins, so there is nothing to migrate.
---

# One command per question, and one rule per flag

## Status

Accepted, 2026-10-28.

## Context

Two spellings of one question mean an agent learns both and the repository keeps two
implementations that can disagree. A flag that makes a judging command write a file combines
with every other flag of that command: a baseline update narrowed by `check --only links` would
delete every other check's entries as fixed. And when one mistake exits differently by command,
a script cannot tell an argument that names nothing from a command that ran and refused.

## Decision

- **Each question has one command, and an old spelling gets no alias.** What this rule removed
  is this record's `retires:` entries, each naming its replacement. `orient` reports source
  ownership coverage with the function `list undocumented` uses, and `irminsul fix` rewrites the
  agent manifest through the fix `agents-manifest` supplies. `change transition` and
  `change finalize` preview without `--confirm`; `fix --dry-run` previews a fix's edits.
- **Writing a maintained file is its own command.** `irminsul baseline init`,
  `baseline update`, `adoption init` and `adoption update` each take only `--path`. The
  baseline pair runs the whole of `checks.enabled`; the adoption pair reads the managed walk,
  never the findings. `check --no-baseline` changes one run and writes nothing.
- **A removed option names its replacement.** `IrminsulGroup` holds one table, `_MOVED`; an
  option it lists exits 2 saying what replaced it, such as `irminsul baseline init` for
  `check --init-baseline`. Other unknown options keep the framework's error. The table is not a
  hidden option, because `irminsul surface cli` would count a hidden option as live.
- **Exit 2 means the invocation was wrong; exit 1 means the command refused on what it found.**
  An argument that names nothing, whether a doc, check, finding code, surface kind, RFC or path,
  exits 2 everywhere. Exit 1 is a failing finding, a dirty tree for `change finalize`, edited
  foundation docs for `seed`, an existing file for `baseline init` or `adoption init`, the
  missing `mcp` extra, or an update that would add an entry. Each such error is a
  `UserError`, whose `code` is 2 unless its raise site says 1.
- **`--only` names any registered check** and takes commas as well as repeats on `check` and
  `fix`: `--only links,orphans`. An empty piece is an unknown name, so `--only ,` cannot run
  everything.
- **`--format` is a choice** of `plain` and `json`, and `github` on `check`; anything else exits
  2.
- **`--committed-only`** is accepted on every command that judges a change, with the meaning
  [A change is judged from its merge base to the working tree](a-change-is-judged-from-its-merge-base-to-the-working-tree.md)
  gives it.

## Alternatives Considered

- **Aliases for old spellings.** Rejected: a second spelling every guide and test must track.
- **Maintenance writes as flags of `check`.** Rejected: the bug is combining `--only` with a
  write, and a list of refused combinations grows with every flag.
- **Exit 1 for an argument that names nothing, as `grep` does.** Rejected: nothing here reads
  "not found" as a result.
- **Split the comma in `select_checks`, which MCP shares.** Rejected: that tool already takes a
  list.

## Consequences

- A script that passes a removed option exits 2 until it names the replacement.
- A bad `--format` gets the CLI framework's wording, not this tool's.
