---
id: 0009-implement-rfc-0018-decision-followups-and-maintenance-queue
title: "ADR-0009: Implement RFC-0018 decision follow-ups and maintenance queue"
audience: adr
tier: 2
status: stable
describes: []
implements:
  - 0018-decision-followups-and-maintenance-queue
summary: Add `followups` and `implements` frontmatter fields, a `decision-followups` soft check, and `irminsul list lifecycle [--queue]` to surface unfinished decision work.
---

# ADR-0009: Implement RFC-0018 decision follow-ups and maintenance queue

## Context

[RFC-0018](../80-evolution/rfcs/0018-decision-followups-and-maintenance-queue.md) identified
a gap: accepted RFCs can close without the downstream docs they affect ever being updated.
Irminsul already detects broken links and stale claims, but it had no way to express "this
decision requires that doc to be updated" as machine-readable metadata. The result was that
follow-up work existed only as prose in Unresolved Questions sections or as informal
post-merge reminders, both of which rot silently.

The RFC also called for a maintenance queue — a single CLI surface that flattens all
unfinished decision work into a prioritised list for agents and developers to triage.

## Decision

Implement RFC-0018 in full:

- Add `FollowupKindEnum` (`create | update | review`) and `FollowupEntry` (structured
  model with `path`, `reason`, `kind`) to `src/irminsul/frontmatter.py`. Add two optional
  fields to `DocFrontmatter`: `followups: list[FollowupEntry] | None` (where `None` means
  the field was never declared, distinct from an explicit empty list) and
  `implements: list[str]` (RFC/ADR IDs this doc operationalises).

- Extend `build_inbound_strong` in `src/irminsul/docgraph_index.py` to index `implements`
  alongside `depends_on`. This makes `implements` back-links available to all checks at
  zero marginal cost via the existing `graph.inbound_strong` index.

- Add `DecisionFollowupsCheck` (`src/irminsul/checks/decision_followups.py`) to the soft
  deterministic registry. It enforces five dimensions:
  1. Accepted RFCs must declare `followups` (even if `[]`).
  2. Every entry in `followups` must resolve to an existing doc.
  3. Every follow-up doc must link back to the RFC via `implements` in `inbound_strong`.
  4. Every `implements` entry must reference a doc that exists in the graph.
  5. Planned claims whose evidence cites an RFC in a resolved state (`accepted`,
     `rejected`, or `withdrawn`) should be updated.

- Add `irminsul list lifecycle [--queue] [--format plain|json]`
  (`src/irminsul/listing/command.py`, `src/irminsul/cli.py`). Without `--queue` it prints
  findings in the same format as `list orphans`. With `--queue` it flattens findings into
  prioritised work items carrying `priority`, `kind`, `target_path`, `related_id`,
  `reason`, and `suggested_command` — designed for agent consumption.

- Register `"decision-followups"` in `SOFT_DETERMINISTIC_CHECKS` in
  `src/irminsul/config.py` and append it to `soft_deterministic` in `irminsul.toml`.

## Alternatives Considered

- **Require `followups` as a hard check.** Rejected: many accepted RFCs affect only
  code, not other docs, and forcing every RFC author to declare `followups: []` before
  merge would add friction without benefit. The soft check surfaces the gap without
  blocking.

- **Use bare string paths in `followups` only.** The RFC permitted bare strings for terse
  use. Rejected in favour of the structured form (`path`, `reason`, `kind`) because the
  queue consumer needs to know the intent (create vs. update vs. review) to produce
  meaningful `suggested_command` values. `reason` defaults to `""` and `kind` to `update`,
  so the structured entry is no more verbose than necessary.

- **Derive `implemented_by` on the RFC from the ADR's `resolved_by`.** The `resolved_by`
  field already exists for this purpose. `implements` generalises the back-link to any
  follow-up doc (component doc, workflow doc, reference doc), not just the decision ADR.
  The two coexist: `resolved_by` points at the decision record; `followups` lists all
  other docs that must be touched.

## Consequences

The check stays soft. Projects opt into strict treatment via `--profile=configured
--strict`. The `followups` and `implements` fields are optional so existing docs remain
valid without back-fill. The `--now` convention from RFC-0017 is not needed here because
the check contains no date comparisons of its own.

The `irminsul refs <rfc-id>` command already exposes `inbound_strong`; extending that
index to include `implements` means `refs` now also surfaces implementer docs without any
additional work.
