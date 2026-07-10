---
id: change
title: Change lifecycle
audience: explanation
tier: 3
status: stable
depends_on:
  - checks
  - config
  - docgraph
  - frontmatter
describes:
  - src/irminsul/change/**
tests:
  - tests/test_change_report.py
  - tests/test_change_transition.py
  - tests/test_cli_change.py
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - change status
      - change verify
      - change transition
---

# Change lifecycle

The `irminsul change` command group treats an RFC as the forward artifact for significant change ([RFC 0029](../80-evolution/rfcs/0029-bound-change-loop.md)): a work item that moves through `draft -> accepted -> implemented`, with `rejected` as the alternate terminal state. The module owns the read-only reports and the confirmed decision transition; the RFC document itself stays the single authored source of intent.

Two linked rules shape every report:

1. **Derive what is mechanically knowable.** Changed files, owning components, test evidence, and check findings come from the diff and the [DocGraph](docgraph.md) on every call; they are never copied onto the RFC.
2. **Expose evidence for semantic judgment.** Whether an implementation satisfies its intent is not derivable. Reports separate mechanical *blockers*, derived *evidence*, and *semantic-review clues* — and may say `mechanically_ready_for`, never "behavior is correct".

## Commands

- `irminsul change status <id>` — lifecycle state (with deprecated-alias resolution), declared `affects`, valid next transitions, a compact evidence summary, and next actions.
- `irminsul change verify <id> [--base-ref REF]` — the full read-only report: blockers, per-file evidence, declared-vs-derived scope divergence, and semantic-review clues, as plain text or versioned JSON.
- `irminsul change transition <id> accepted|rejected --confirm` — validate and apply a human-authorized decision atomically: `rfc_state`, `status: stable`, `resolved_by`, an empty `required_updates`, and the terminal scaffolding section land in one confirmed pass, reusing the dry-run/confirm contract of `fix`. `implemented` is deliberately not a valid target here; only finalization may write it.

## Requirements as review contracts

Behavior-changing RFCs carry a `## Requirements` section ([RFC 0030](../80-evolution/rfcs/0030-rfc-requirements-and-scenarios.md)): requirement blocks with a stable local id, an evidence obligation (`Provenance: code|adr|citation`), SHALL/MUST behavior text, and named WHEN/THEN scenarios. A maintenance RFC instead writes the explicit sentence `No new behavioral requirements: ...` — reviewable intent, not silent omission. Reports surface each requirement with its globally addressable id `<rfc-id>#<requirement-id>`; a `Provenance: code` requirement stays an unbound evidence obligation until finalization binds it to an anchored claim. Grammar findings are warnings while drafting and blockers at `change transition ... accepted`.

## Tasks and implementation evidence

An RFC records its accepted implementation plan as a static `## Tasks` list ([RFC 0031](../80-evolution/rfcs/0031-change-tasks-and-apply.md)): ordinary list items with stable ids that reference a requirement id or a declared affected component — never assignees, deadlines, or status fields. `change status` and `change verify` (and `irminsul context --change <id>`) gather the mechanical evidence around each task: changed source owned by the referenced components, changed tests named by their component docs, and a review clue when evidence is absent. Counts are named precisely (`2/3 tasks with source evidence`), never rendered as percent complete: changed files are evidence, not proof that a free-text task is done. Irminsul does not implement tasks — the agent inspects the evidence, edits, and re-runs the report.

## Diff baseline

Evidence needs a comparison range, and the resolver never guesses a clean result: an explicit `--base-ref`, a CI-provided base ref (`IRMINSUL_BASE_REF` or `GITHUB_BASE_REF`), or the local staged/unstaged/untracked set — in that order. When none is available the baseline is reported as `unknown`, which can never be mechanically ready for finalization.

## Scope & Limitations

The module does not implement tasks, judge semantic completion, or transition an RFC on its own conclusions — acceptance and rejection are human decisions it validates and records. The declared-versus-derived footprint comparison is shared with the `change-binding` soft check registered in [checks](checks.md). Requirements, task evidence, finalization, and layered impact arrive with the later RFCs in the 0029–0034 stack.
