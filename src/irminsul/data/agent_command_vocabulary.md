# Agent command vocabulary

This file is the single source of truth for the curated command vocabulary that
`irminsul orient` emits as its `commands` field. It is tracked, reviewable
Markdown rather than a Python literal so the vocabulary can be edited and audited
on its own.

The vocabulary is a *curated subset* of the CLI surface, not the whole of it:
the surface is derivable on demand (`irminsul surface cli`), but the **when** —
which command to reach for at each step of the edit-verify loop — is intent, and
only a human curates it.

The `command-vocabulary` check keeps this file honest against the live CLI
surface: it warns when an entry names a command that no longer exists, when an
entry has no guidance, when the omitted list names a command that is gone, and
when a new top-level command is neither taught here nor explicitly omitted. When
that last warning fires, decide which list the new command belongs in.

## Commands

| command | when |
| --- | --- |
| `irminsul context --changed` | before and after editing: see which docs own your edits, their tests, and findings |
| `irminsul context --topic <query>` | find the docs that cover a topic before starting work |
| `irminsul context <path>` | look up the owning doc, tests, and dependencies for one file |
| `irminsul refs <doc-or-symbol>` | enumerate inbound references before renaming or moving anything |
| `irminsul surface <kind> --format json` | derive the current code surface (cli, http, exports, env-vars) instead of trusting prose |
| `irminsul check --profile=hard --format json` | verify the docs tree before committing; error findings block CI |
| `irminsul fix` | auto-apply deterministic remediations for fixable findings |
| `irminsul list undocumented` | find source files in covered directories that no doc claims |

## Omitted

Top-level commands intentionally absent from the vocabulary above — bootstrap,
situational, or the orientation command itself. Listing them here is a deliberate
acknowledgement, so that a genuinely new command surfaces as a warning instead of
slipping in unnoticed.

- `anchors`
- `init`
- `init-docs-only`
- `new`
- `orient`
- `regen`
- `seed`
