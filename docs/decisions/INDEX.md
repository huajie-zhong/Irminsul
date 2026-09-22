---
id: decisions
title: Architecture decisions
status: stable
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
- **Decisions are not rewritten in place.** If a decision changes, record the change in a new ADR. Periodically, settled decisions are consolidated into themed records and the originals removed; git history keeps them.
- **The "Alternatives Considered" section is mandatory.** Without it, future contributors will keep proposing the same rejected ideas.
- **Write the smallest record that is reviewable.** For an ordinary policy or configuration change, three things have to be obvious at a glance: what changes — name the setting and give both values, `mtime_drift_days` 30 → 3650; the concrete reason; and what protection is gained or lost, which findings stop being reported. Background a reader can reconstruct, and justification for a decision nobody disputed, are what makes a record go unread. A decision that genuinely needs the length may take it — the records here run from 41 to 117 lines — but length is earned by the decision, not by the template.
- **A record makes a weakening visible, not authorised.** `diff-integrity` clears a weakened setting when an added stable record names it, and that is all it establishes: a reason exists in writing, where the reviewer and every later change inherit it. The same author can write both in one commit. Whether the reason is good, and whether that person may decide it, is a question about people and permissions that no check in this repository can answer — it lives in review and in the forge's branch protection ([enforcement](../foundation/enforcement.md)).

Current records:

- [Documentation model](documentation-model.md)
- [Deterministic enforcement](deterministic-enforcement.md)
- [Derive, don't materialize](derive-dont-materialize.md)
- [Change lifecycle](change-lifecycle.md)
- [Agent interface](agent-interface.md)
- [Adoption and repository layouts](adoption-and-repository-layouts.md)
- [Ship framework packs with kind capabilities](ship-framework-packs-with-kind-capabilities.md)
- [Mark review items by symbol freshness](mark-review-items-by-symbol-freshness.md)
- [Finding classes decide what blocks](finding-classes-decide-what-blocks.md)
- [Baseline holds certain findings and only shrinks](baseline-holds-certain-findings-and-only-shrinks.md)
- [Git history seals implemented records](git-history-seals-implemented-records.md)
- [Records are named by slug](records-are-named-by-slug.md)
- [Anchors bind code names in any language](anchors-bind-code-names-in-any-language.md)
- [Docs carry no audience field](docs-carry-no-audience-field.md)
- [Splitting a doc keeps one description of the code](splitting-a-doc-keeps-one-description.md)
- [Weakening the config needs a decision record](weakening-the-config-needs-a-decision-record.md)
- [Switching a check off is more than a list edit](switching-a-check-off-is-more-than-a-list-edit.md)
- [Drafts excuse an unfinished doc not a wrong one](drafts-excuse-an-unfinished-doc-not-a-wrong-one.md)
- [Unclaimed code in documented territory is an error](unclaimed-code-in-documented-territory-is-an-error.md)
- [Removing a claim about surviving code is a finding](removing-a-claim-about-surviving-code-is-a-finding.md)
- [Authority follows the kind of claim](authority-follows-the-kind-of-claim.md)
- [Context keeps no session; external checks may cache observations](context-keeps-no-session-external-checks-may-cache-observations.md)
- [A governing claim ends by decision, not by deleting its evidence](a-governing-claim-ends-by-decision-not-by-deleting-its-evidence.md)
- [A snapshot is judged by its own configuration](a-snapshot-is-judged-by-its-own-configuration.md)
