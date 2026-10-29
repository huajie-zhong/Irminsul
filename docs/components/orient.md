---
id: orient
title: Agent orientation command
status: stable
depends_on:
  - config
  - docgraph
describes:
  - src/irminsul/orient.py
owns_tests:
  - tests/test_cli_orient.py
summary: The first call for agents — repo structure, doc totals, source ownership coverage, entry docs and commands as one report.
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    complete: true
    items:
      - context
      - refs
      - surface
      - check
      - fix
      - list undocumented
      - list lifecycle
      - list review
      - change status
      - new rfc
    omit:
      - adoption init
      - adoption update
      - anchors
      - baseline init
      - baseline update
      - explain
      - change finalize
      - change transition
      - change verify
      - init
      - list baseline
      - mcp
      - new adr
      - new component
      - orient
      - seed
---

# Agent orientation command

`irminsul orient` is the single entry point for agents working in an Irminsul-managed repo: run it first. It builds the [DocGraph](docgraph.md) once, reads [config](config.md), and runs only the enabled checks that report time findings without the network, so it is fast. `OrientReport` is the report and `--format json` prints it; its `commands` field teaches the rest of the vocabulary ([Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)).

Source ownership coverage is in the report because no check reports it: an unowned file outside every documented directory raises no finding, so a repository of undocumented code keeps `check` green. It comes from the helper `irminsul list undocumented --all` lists from, so the two cannot disagree. Of the entry docs only the root harness router ([`AGENTS.md`](../../AGENTS.md)) is probed at the repo root: other conventional names would duplicate their docs-root counterparts. Time findings are shown because a diff leaves them out, so no pull request shows what elapsed time made stale; `external-links` is not run, and `irminsul check --fail-on time` covers it.

## Scope & Limitations

The report is a snapshot of structure, not health: apart from time findings it reports no findings. The command vocabulary is curated and static, since `irminsul surface cli` derives the full surface, but its command identities are kept honest against that surface by the `inventory:` block above (`complete: true`): `inventory-drift` flags a renamed or removed taught command, a new one neither taught nor excluded, and a stale `omit` entry. It is name-based, so a stale `when` description is left to human review. Entry docs are detected by filename convention only.
