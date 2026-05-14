---
id: 0018-decision-followups-and-maintenance-queue
title: Decision followups and maintenance queue
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0018: Decision followups and maintenance queue

## Summary

Add explicit follow-up tracking for accepted decisions and a lifecycle listing
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
followups:
  - docs/20-components/example.md
implements:
  - 0017-rfc-resolution-check
```

`followups` belongs primarily on RFCs and ADRs. It lists docs or generated
surfaces that must be created, updated, or reviewed before the decision is
considered fully integrated.

`implements` belongs on ADRs, component docs, workflow docs, and reference docs.
It lists RFC or ADR IDs that the doc implements or operationalizes.

Add a command:

```text
irminsul list lifecycle
```

The command reports:

- accepted RFCs without `resolved_by`
- accepted RFCs without follow-ups or an explicit empty `followups: []`
- follow-up paths that do not exist
- follow-up docs that do not link back to the RFC or ADR
- docs with `implements` entries pointing at missing or unresolved decisions
- planned claims whose cited RFC is accepted, rejected, or withdrawn
- foundation or architecture docs changed after dependent stable docs, requiring
  review

The command is read-only and supports `--format plain|json`, matching existing
list commands.

Add a soft deterministic check named `decision-followups` that emits the same
core findings during `irminsul check --profile configured`. Keep the list
command as the human-friendly queue view.

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

- Use GitHub issues for follow-ups. Rejected because Irminsul must work without
  hosted state and because lifecycle health should be visible from the docs
  tree.
- Depend only on `mtime-drift`. Rejected because file modification time cannot
  express which decision a doc is meant to implement.
- Make every accepted RFC require implementation code. Rejected because some
  accepted RFCs are process or documentation changes.

## Unresolved Questions

- Should `followups: []` be required on every accepted RFC, or only on RFCs that
  affect docs outside the RFC itself?
- Should `irminsul list lifecycle` include supersession warnings, or should it
  stay focused on decision follow-through?
