---
id: agent-protocol
title: Agent lifecycle protocol
audience: explanation
tier: 3
status: stable
describes: []
summary: The required work order any agent must follow when editing this repository.
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - orient
      - context
      - check
      - regen agents-md
      - list lifecycle
      - change status
      - change verify
      - change transition
      - change finalize
---

# Agent lifecycle protocol

This document defines the work order an agent must follow when editing this
repository. The agent navigation manifest at [`AGENTS.md`](../AGENTS.md) is the
entry point; it summarizes the doc system and deep-links here.

The protocol is universal — it applies to any project that uses Irminsul, not
just this one. Follow each step in order; do not skip ahead.

## Work order

0. **Orient first.** Run `irminsul orient` (or `irminsul orient --format json`)
   to load the repo's structure, doc totals, entry docs, and command
   vocabulary, then read [`AGENTS.md`](../AGENTS.md) before any other step.
   The manifest names the layers and tiers, the Three Laws, and this protocol.
   If the manifest is missing or its generated section is stale, run
   `irminsul regen agents-md` and proceed.

1. **Locate context before editing.** Run
   `irminsul context --before-edit <target...>` to package ownership,
   dependencies, tests, active RFCs, and relevant findings for the work ahead.
   Use the path, topic, and changed modes directly when a focused power-tool
   query is more appropriate.

2. **Update the foundation before the implementation.** If the request changes
   project direction, update the foundation docs or create an RFC before
   changing implementation.

3. **Create or update an RFC for significant change.** If the work proposes a
   significant behavior, architecture, lifecycle, CLI, or check change, create
   or update an RFC.

4. **Resolve accepted RFCs with an ADR.** When an RFC is accepted, create or
   update an ADR and link the RFC to that decision record. The decision itself
   is human-authorized: apply it with
   `irminsul change transition <id> accepted --confirm` only after the user has
   approved it.

4a. **Work the bound-change loop for accepted RFCs.** Discover accepted work
   with `irminsul list lifecycle --queue`, orient with
   `irminsul change status <id>`, implement, then run
   `irminsul change verify <id>` and resolve its mechanical blockers and
   semantic-review clues. When the report is mechanically ready and the user
   has authorized completion, run `irminsul change finalize <id> --confirm`
   with the reviewed `--anchor` bindings — finalization is the only path to
   `rfc_state: implemented`.

5. **Keep component docs honest.** When code is added or moved, create or
   update component docs with up-to-date `describes` mappings and tests
   metadata. Before renaming or moving a code symbol, doc, or directory, run
   `irminsul refs <symbol-or-path>` to enumerate strong and weak inbound
   references, and update each before completing the move.

6. **Keep workflow and reference docs current.** When workflows, commands, or
   reference surfaces change, update the corresponding workflow, component,
   or generated reference docs.

7. **Supersede deliberately.** When a doc replaces another doc, use
   `supersedes` on the new doc and run `irminsul fix` to update the old doc's
   metadata.

8. **Validate after editing.** Run `irminsul context --after-edit`, resolve its
   hard-validation errors and deterministic next actions, then run
   `irminsul check --profile hard` as the final gate. For larger work, also run
   `irminsul check --profile configured` and `irminsul list undocumented`.

9. **Report remaining signal.** Report any remaining warnings, skipped checks,
   or follow-up decisions in the final response.

## Scope & Limitations

- This protocol covers the work order; it does not enumerate doc-system
  rules (those live in [`CONTRIBUTING.md`](../CONTRIBUTING.md)) or coding
  conventions (those live in the project's own style guide).
- Steps 8–9 require running `irminsul check`; the protocol does not itself
  define which checks are hard or soft — that is the province of
  the check registry in `src/irminsul/checks/__init__.py` and the
  project's `irminsul.toml`.
- Violations are not yet enforced by a mechanical check; later RFCs add
  targeted checks for individual transitions (e.g. RFC resolution).

## Rationale and alternatives

The rationale, drawbacks, and rejected alternatives for this protocol live in
[`0016-agent-lifecycle-protocol`](../80-evolution/rfcs/0016-agent-lifecycle-protocol.md).
