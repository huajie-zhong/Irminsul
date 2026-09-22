---
id: docs-carry-no-audience-field
title: "Docs carry no audience field"
status: stable
describes: []
summary: The required audience frontmatter field is removed; a decision record is known by its layer, and writing for one reader stays a writing rule, not metadata.
---

# Docs carry no audience field

## Status

Accepted, 2026-09-15.

## Context

Every doc declared `audience`: one of tutorial, howto, reference, explanation, adr,
runbook, or meta. Only two uses changed behaviour. `adr` marked a decision record for
four checks, which the decisions layer already says. `explanation` and `reference` chose
the docs `liar` scans. The other values were labels nothing read, and no check could tell
whether a label was true, so a required field held information the tool could not keep
honest.

## Decision

- **The field is removed** from the frontmatter schema, the scaffolds, the `new` and
  `seed` templates, the manifest table, and `context` output.
- **A decision record is a doc in the decisions layer** other than its INDEX, for
  `adr-structure`, `orphans`, live-doc detection, `retired-references`, and
  `diff-integrity`.
- **`liar` scans live docs outside the guides layer**, where a guide demonstrates
  commands step by step rather than enumerating a surface.
- **Writing for one reader stays a rule** in the contributing guide and the principles.
- **No tombstone.** A leftover `audience` key is an unknown frontmatter key, which the
  schema accepts and nothing reads.

## Alternatives Considered

- **Keep the field and add wording checks per audience.** Rejected: a list of tutorial
  phrases is a weak signal for a label that changes no behaviour.
- **Make the field optional.** Rejected: an optional label nothing reads still invites
  maintenance and drift.

## Consequences

- Docs are one line shorter, and a doc no longer needs a label to pass.
- Guides are exempt from `liar` by location, so a reference table placed in a guide is
  not scanned.
