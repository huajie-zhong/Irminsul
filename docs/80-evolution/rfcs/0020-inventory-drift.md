---
id: 0020-inventory-drift
title: Inventory drift for endpoints, commands, and exports
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0020: Inventory drift for endpoints, commands, and exports

## Summary

Add an optional `inventory` frontmatter field on component docs and a soft
deterministic check `inventory-drift` that compares the declared inventory
against the actual surface extracted from the code the doc describes.

## Motivation

Component docs can claim `commands: [irminsul check]` or `endpoints: [GET
/api/check]` today with nothing verifying these against the code. RFC-0010
handles structured *evidence* for individual claims, but it does not compare a
declared inventory against the actual code surface. Drift accumulates silently
until a human or LLM notices.

This is the missing deterministic counterpart to RFC-0010: where RFC-0010 asks
"does this claim point at evidence," `inventory-drift` asks "does this complete
list match the code."

A concrete instance this RFC must catch: the `new-list-regen` component doc
enumerated the `irminsul regen` subcommands in prose. When `regen agents-md`
was added, the doc was not updated and nothing flagged it — the prose silently
went stale. `cli-doc-drift` (RFC-0009) did not catch it because that check only
compares the *generated* CLI reference against Typer, not hand-written
component prose. The design below must flag this case even though the stale doc
carried no structured inventory and does not `describes` the file where the
commands are defined.

## Detailed Design

### Frontmatter shape

```yaml
inventory:
  kind: cli            # cli | http | exports | env-vars
  source: src/irminsul/cli.py   # optional; defaults to the doc's describes globs
  items:
    - irminsul check
    - irminsul context
    - irminsul fix
```

`kind` selects the extractor; `items` declares the canonical list. The optional
`source` path points the extractor at the code that defines the surface — it
defaults to the doc's `describes` globs, but a doc often documents a surface
that is *defined* elsewhere (CLI commands are registered in a central
entrypoint like `src/irminsul/cli.py`, not in the implementation modules the
doc `describes`). Without `source`, such a doc could never diff cleanly.

### Per-language extractors

Reuse the existing `src/irminsul/languages/` plugin pattern (already used for
source-root candidates and schema-leak regexes):

- **Python/Typer** (dogfood target). AST-walk files matching the doc's
  `describes` glob; collect `@app.command(...)` decorators and Typer
  subcommand functions; emit the actual command list.
- **Python/FastAPI**. Route decorators (`@app.get`, `@app.post`, …) → HTTP
  inventory.
- **TypeScript**. Reuse the TypeDoc surface produced by RFC-0012 → exported
  names or route registrations.
- **Generic regex fallback**. A per-language regex declared in `irminsul.toml`
  for languages without a plugin.

### Check semantics

Add `inventory-drift` to the soft deterministic registry. It compares each
extracted code surface against the union of all `inventory:` blocks of the same
`kind` across the doc graph:

- *Claimed in a doc inventory, missing in code* → error. Lies in the doc.
- *Present in code, not in any doc inventory of that kind* → soft. The surface
  item is undocumented. Potentially intentional (hidden commands, internal
  endpoints) but worth surfacing.

The second direction is surface-wide on purpose: it does not matter *which* doc
ought to own a given command — if a command exists and no inventory anywhere
lists it, that is the finding. This is what would have caught `regen agents-md`.

### Docs that should declare an inventory

The check is only useful if docs that document an inventoried surface actually
carry the field. So `inventory-drift` also emits a soft finding when a
component doc describes or names a surface an extractor recognizes — for the
CLI extractor, a doc whose body contains command-signature headings or
`irminsul <subcommand>` prose patterns — but declares no `inventory:` block.
This is the rule that closes the prose-drift hole directly: a doc listing
commands in prose with no structured inventory is flagged so the gap is fixed
before the prose can rot. The `new-list-regen` doc would be flagged by this
rule today.

Both kinds of finding name the specific items so a fix is unambiguous.

### Auto-fix

Replace the `inventory:` block with the extractor's output. The fix is atomic
and lands inside RFC-0022's rollout.

### Dogfood

Irminsul itself is a Typer CLI, so the Python/Typer extractor lands first and
validates the CLI component docs against `src/irminsul/cli.py`. This catches
drift in the very command list agents rely on for navigation. The acceptance
bar for the dogfood extractor is the `regen agents-md` incident: with this RFC
implemented, adding a subcommand without updating its component doc must
produce a finding — either an unclaimed-surface finding (the command is in code
but no inventory lists it) or a missing-inventory finding (the documenting doc
still lists commands only in prose).

## Relationship to Existing RFCs

- Complements RFC-0010 (claim provenance): evidence vs. inventory.
- Reuses the language plugin layout established for source-root and
  schema-leak handling.
- TypeScript inventory builds on RFC-0012's TypeDoc reference surface.
- Auto-fix lands as part of RFC-0022.

## Drawbacks

Each extractor is its own surface area. The plugin pattern keeps additions
contained, but a poorly written extractor could produce false positives. The
check stays soft for that reason; promotion to hard is left to projects whose
extractors are mature.

## Alternatives

- Require docs to enumerate inventory in prose. Rejected because prose cannot
  be diffed deterministically. Note this is *not* the same as the
  missing-inventory rule above: that rule detects a doc relying on prose and
  tells it to adopt the structured field — it never tries to diff the prose
  itself.
- Treat inventory as another evidence kind under RFC-0010. Rejected because
  inventories are list-shaped and benefit from a dedicated diff, not a
  per-item evidence pointer.
- Generate the inventory from code only, never from doc frontmatter. Rejected
  because human-curated ordering and grouping is sometimes load-bearing.

## Unresolved Questions

- Should `items` allow grouped sub-lists (e.g., command groups), or should
  groups be a separate field?
- For HTTP inventories, should query parameters and request bodies be part of
  the canonical surface, or stay out of scope for this RFC?
