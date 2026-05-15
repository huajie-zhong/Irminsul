---
id: 0017-rfc-resolution-check
title: RFC resolution check
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
resolved_by: docs/50-decisions/0008-implement-rfc-0017-rfc-resolution-check.md
followups: []
---

# RFC 0017: RFC resolution check

## Summary

Add a deterministic soft check named `rfc-resolution` that validates RFC
lifecycle state. The check makes sure resolved RFCs become reliable historical
records and accepted RFCs point to the ADR or decision doc that carries the
canonical decision forward.

## Motivation

The frontmatter schema already has `rfc_state` and requires `resolved_by` when
`rfc_state: accepted`, but the lifecycle is incomplete. A resolved RFC can stay
`status: draft`, accepted proposals can fail to link to an existing ADR, and the
RFC index can say a process exists that no check actually enforces.

This is the specific gap where agents lack enforcement after RFC completion.
Once a proposal is accepted, the agent should mark the RFC as a stable record,
create or update the ADR, link both directions, and update affected docs.

## Detailed Design

Add `rfc-resolution` to the deterministic soft registry.

For docs under `docs/80-evolution/rfcs/`:

- `rfc_state: accepted` requires `resolved_by`.
- `resolved_by` must point to an existing Markdown doc.
- Accepted RFCs should have `status: stable`.
- Rejected RFCs should also have `status: stable` once the rejection rationale
  is recorded. They should include a `## Resolution` section (or a more
  specific `## Rejection Rationale` section).
- Withdrawn RFCs (`rfc_state: withdrawn`) should have `status: stable`, must
  include a `## Withdrawal Rationale` section (or reuse `## Resolution` if the
  rationale is short), do not require `resolved_by`, and should not retain a
  non-empty `## Unresolved Questions` section.
- Resolved RFCs should include a `## Resolution` section.
- Accepted RFCs should not have a non-empty `## Unresolved Questions` section
  unless the body explicitly names follow-up work.
- The resolved-by doc should link back to the RFC.

### Atomicity

Accepting an RFC requires `rfc_state: accepted`, `status: stable`, and
`resolved_by` to be set in a single edit. The check catches inconsistency
post hoc; `irminsul fix` (per RFC-0022) provides an atomic helper that
performs all three on confirm and inserts a stub `## Resolution` section.

### Time Handling

The `target_decision_date` comparison defaults to the system UTC date at
check-run time, so behavior is consistent across CI runners in different
timezones. A `--now YYYY-MM-DD` flag overrides the comparison basis for
deterministic test fixtures. Other date-sensitive checks adopt the same
convention.

Add these optional RFC frontmatter fields:

```yaml
decision_owner: ""
target_decision_date: "YYYY-MM-DD"
```

If an RFC is `draft`, `open`, or `fcp` and `target_decision_date` is in the
past, the check emits a warning. If `decision_owner` is missing on an open RFC,
the check emits a warning.

The check should stay soft at first. A project can opt into strict treatment by
running configured checks with `--strict` after the process proves useful.

## Relationship to Existing RFCs

This RFC extends the structured claim lifecycle from
[`0010-structured-claim-provenance`](0010-structured-claim-provenance.md). It
also supports the agent lifecycle protocol proposed in
[`0016-agent-lifecycle-protocol`](0016-agent-lifecycle-protocol.md).

## Drawbacks

The check cannot prove that an ADR fully implements an RFC's intent. It can only
prove lifecycle structure: state, links, and required follow-up markers.

Resolved RFCs without a clean ADR mapping may need a short migration period.
That is why the check starts as soft.

## Alternatives

- Keep RFC lifecycle as prose in the evolution index. Rejected because agents
  need machine-readable feedback.
- Make accepted RFCs move into the ADR folder. Rejected because RFCs are useful
  historical artifacts and should remain in the evolution layer.
- Treat `status: stable` as the acceptance state. Rejected because doc
  reliability and proposal outcome are separate concepts.

## Resolution

Accepted and implemented in
[ADR-0008](../../50-decisions/0008-implement-rfc-0017-rfc-resolution-check.md).
The check ships in `src/irminsul/checks/rfc_resolution.py` with tests in
`tests/test_checks_rfc_resolution.py` and a `--now YYYY-MM-DD` flag on
`irminsul check` so date-sensitive checks share one source of "today".

Two open design questions were settled during implementation:

- **`resolved_by` accepts paths**, matching the existing schema. Doc IDs were
  not added; the existing path string is unambiguous and survives renames
  about as well as IDs do.
- **Rejected RFCs may carry either `## Resolution` or
  `## Rejection Rationale`.** The check accepts either, since the cost of
  forcing a specific heading on already-closed proposals outweighs the
  benefit.
