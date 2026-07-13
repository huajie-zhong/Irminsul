---
id: 0018-decision-followups-and-maintenance-queue
title: Decision required updates and maintenance queue
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
affects: [checks, new-list-regen]
resolved_by: docs/50-decisions/0009-implement-rfc-0018-decision-followups-and-maintenance-queue.md
required_updates: []
---

# RFC 0018: Decision required updates and maintenance queue

## Summary

Add explicit required update tracking for accepted decisions and a lifecycle listing
command that gives agents a durable maintenance queue. The queue surfaces
accepted RFCs that have not updated downstream docs, implementation records, or
planned claims.

## Motivation

Irminsul can detect broken links, unresolved globs, stale generated references,
and some stale claims. It still lacks a durable view of "what decision work is
unfinished." That means accepted RFCs can complete without component docs,
workflow docs, generated references, or implementation links being updated.

The tool should make unfinished decision fallout visible before it becomes
long-term documentation rot.

## Detailed Design

Add optional frontmatter fields:

```yaml
required_updates:
  - path: docs/20-components/example.md
    reason: Add coverage for the new check
    kind: update           # create | update | review
implements:
  - 0017-rfc-resolution-check
```

`required_updates` belongs primarily on RFCs and ADRs. It lists docs or generated
surfaces that must be created, updated, or reviewed before the decision is
considered fully integrated. Each entry carries a `reason` so the queue can
explain why an item matters, and a `kind` so the agent knows whether to
create, update, or merely review the target. Entries use the structured form
because the queue is the primary consumer.

`implements` belongs on ADRs, component docs, workflow docs, and reference docs.
It lists RFC or ADR IDs that the doc implements or operationalizes.
`implements` is the *source of truth* for the decision-to-doc relationship.
The inverse (`implemented_by` on the RFC or ADR) is auto-derived at graph-build
time following the existing inbound-index pattern (`docgraph_index.py`) and
exposed through `irminsul refs <rfc-id>` (per RFC-0014). This requires extending
the strong-reference collection in `build_inbound_strong`, which today indexes
only `depends_on`, to also index `implements` and the implicit `resolved_by`
ADR relationship. Authors do not maintain the back-link manually; the check
that required update docs link back to the RFC is satisfied by the presence of
`implements` on the required update doc. The canonical ADR named by
`resolved_by` is implicit and does not need to be listed in `required_updates`.

Add a command:

```text
irminsul list lifecycle
```

The command reports:

- accepted RFCs without `resolved_by`
- accepted RFCs without required updates or an explicit empty `required_updates: []`
- required update paths that do not exist
- required update docs that do not link back to the RFC or ADR
- docs with `implements` entries pointing at missing or unresolved decisions
- planned claims whose cited RFC is accepted, rejected, or withdrawn
- foundation or architecture docs changed after dependent stable docs, requiring
  review

The command is read-only and supports `--format plain|json`, matching existing
list commands.

### Unified queue mode

`irminsul list lifecycle --queue` flattens all seven dimensions above into one
sorted work list for agents that want a single triage surface. Each queue
item carries:

- `priority` — overdue decision dates first, then missing required updates, then
  drift signals.
- `kind` — `create`, `update`, `review`, or `resolve`.
- `target_path` — the doc that needs action.
- `related_rfc` or `related_adr` — the decision driving the work.
- `reason` — copied from the `required_updates` entry where applicable.
- `suggested_command` — the next CLI invocation (for example,
  `irminsul fix --check ...` or `irminsul new component ...`).

`--format json` produces the same structure machine-readably for agent
consumption. The non-queue mode remains the human-friendly view.

Add a soft deterministic check named `decision-updates` that emits the same
core findings during `irminsul check --profile configured`. Keep the list
command as the human-friendly queue view, and `--queue` as the agent-friendly
worklist.

## Relationship to Existing RFCs

This RFC builds on structured claims from
[`0010-structured-claim-provenance`](0010-structured-claim-provenance.md), agent
context from [`0011-agent-context-command`](0011-agent-context-command.md), and
the RFC resolution check proposed in
[`0017-rfc-resolution-check`](0017-rfc-resolution-check.md).

## Drawbacks

Follow-up metadata is another field authors and agents must maintain. The value
is that the field turns an otherwise invisible responsibility into an auditable
queue.

Foundation drift warnings may be noisy because intent changes do not always
invalidate downstream docs. The warning should ask for review, not claim the
downstream doc is wrong.

## Alternatives

- Use GitHub issues for required updates. Rejected because Irminsul must work without
  hosted state and because lifecycle health should be visible from the docs
  tree.
- Depend only on `mtime-drift`. Rejected because file modification time cannot
  express which decision a doc is meant to implement.
- Make every accepted RFC require implementation code. Rejected because some
  accepted RFCs are process or documentation changes.

## Resolution

Implemented as specified; see
[ADR-0009](../../50-decisions/0009-implement-rfc-0018-decision-followups-and-maintenance-queue.md).

The two unresolved questions were settled during implementation:

- **`required_updates` requirement scope**: The `decision-updates` check warns whenever
  an accepted RFC has no `required_updates` field at all. Authors must explicitly
  write `required_updates: []` to acknowledge that no downstream docs beyond the
  canonical `resolved_by` ADR need updating. This keeps the field's absence
  distinguishable from a deliberate empty declaration.

- **Supersession warnings**: `irminsul list lifecycle` stays focused on decision
  follow-through only. Supersession drift is already handled by `SupersessionCheck`
  and surfaced via `irminsul check`; merging the two surfaces would dilute the queue's
  signal.
