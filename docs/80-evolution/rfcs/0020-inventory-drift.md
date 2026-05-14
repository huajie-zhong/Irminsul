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

## Detailed Design

### Frontmatter shape

```yaml
inventory:
  kind: cli            # cli | http | exports | env-vars
  items:
    - irminsul check
    - irminsul context
    - irminsul fix
```

`kind` selects the extractor; `items` declares the canonical list. The field is
optional and only meaningful on component docs whose `describes` paths point at
real code.

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

Add `inventory-drift` to the soft deterministic registry:

- *Claimed in doc, missing in code* → error. Lies in the doc.
- *Present in code, unclaimed in doc* → soft. Potentially intentional (hidden
  commands, internal endpoints) but worth surfacing.

Both kinds of finding name the specific items so a fix is unambiguous.

### Auto-fix

Replace the `inventory:` block with the extractor's output. The fix is atomic
and lands inside RFC-0022's rollout.

### Dogfood

Irminsul itself is a Typer CLI, so the Python/Typer extractor lands first and
validates the CLI component doc against `src/irminsul/cli.py`. This catches
drift in the very command list agents rely on for navigation.

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
  be diffed deterministically.
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
