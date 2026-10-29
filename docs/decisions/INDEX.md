---
id: decisions
title: Architecture decisions
status: stable
summary: ADRs are the canonical home for why; this index gives their template and the rules every record follows.
describes: []
---

# Architecture decisions (ADRs)

ADRs are the canonical home for *why*. Use the standard template (Michael Nygard's original works fine):

```
# Adopt event sourcing for the order service

## Status
Accepted, 2026-04-01. Supersedes [Store orders in one table](store-orders-in-one-table.md).

## Context
What forces are at play? What are we currently doing?

## Decision
What we will do.

## Alternatives Considered
What we explicitly rejected, and why.

## Consequences
What becomes easier. What becomes harder. What new risks appear.
```

Four non-obvious rules:
- **A record is a living topic.** Each record lists under `governs:` the files, parts of files and settings it decides, and no two records govern one item. A changed decision is edited in place, with a dated item in a closing `## Changes` section, and a new record is written only for something no record governs ([Decision records govern what they decide](../rfcs/decision-records-govern-what-they-decide.md), accepted and not yet implemented). Until its checks land, nothing reads `governs:`, and the weakening excuse of the fourth rule still asks for an added record.
- **The "Alternatives Considered" section is mandatory.** Without it, future contributors will keep proposing the same rejected ideas.
- **Write the smallest record that is reviewable.** For an ordinary policy or configuration change, three things have to be obvious at a glance: what changes — name the setting by its dotted name and give both values, `overrides.mtime_drift_days` 30 → 3650; the concrete reason; and what protection is gained or lost, which findings stop being reported. Background a reader can reconstruct, and justification for a decision nobody disputed, are what makes a record go unread. A decision that genuinely needs the length may take it, but length is earned by the decision, not by the template.
- **A record makes a weakening visible, not authorised.** `diff-integrity` clears a weakened setting when an added stable record names it, and that is all it establishes: a reason exists in writing, where the reviewer and every later change inherit it. The same author can write both in one commit. Whether the reason is good, and whether that person may decide it, is a question about people and permissions that no check in this repository can answer — it lives in review and in the forge's branch protection ([enforcement](../foundation/enforcement.md)).
