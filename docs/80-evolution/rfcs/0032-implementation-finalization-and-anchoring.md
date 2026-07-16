---
id: 0032-implementation-finalization-and-anchoring
title: "Implementation finalization and anchored claims"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: implemented
affects:
- anchors
- change
- frontmatter
resolved_by: docs/50-decisions/0016-freeze-implemented-rfc-records.md
required_updates: []
frozen_hash: "sha256:4814045661569962775f676f13aeaf8b144db9975baf65b44fbbe80997a09d15"
---

# RFC 0032: Implementation finalization and anchored claims

## Summary

Add `irminsul change finalize <id>` as the only transition from an accepted RFC
to an implemented RFC. Finalization verifies mechanical preconditions, presents
semantic-review clues, promotes code-backed requirements into the owning component
docs as anchored claims, and changes `rfc_state` to `implemented` atomically.

The resulting anchor is a persistent freshness tripwire, not proof of behavior. It
can establish that the confirmed evidence symbol exists and has or has not changed
since review; tests, agents, and humans still judge whether the requirement is
semantically satisfied.

## Motivation

Acceptance and implementation are different events. `rfc_state: accepted` means a
human approved the proposal for work; it must not imply that satisfying code exists.
The current repository has no RFC-specific command that checks implementation
evidence, guides semantic review, promotes durable claims, or records completion.

Irminsul already has the required mechanical primitives:

- anchored prose claims and content hashes
  ([`0024-anchored-prose-claims`](0024-anchored-prose-claims.md));
- claim provenance
  ([`0010-structured-claim-provenance`](0010-structured-claim-provenance.md));
- RFC-to-ADR resolution
  ([`0017-rfc-resolution-check`](0017-rfc-resolution-check.md));
- required-update backlinks and fixes;
- component ownership and coverage.

What is missing is the governed transition that composes them and makes unfinished
accepted RFCs visible.

## Detailed Design

### Verification before mutation

`irminsul change finalize <id>` first runs the same read-only report as
`change verify`. The RFC must:

1. be `rfc_state: accepted` and resolve to its ADR;
2. declare `affects`, including explicit `[]` when no source is intended;
3. have valid requirements or an explicit no-new-behavior disposition;
4. have a usable diff baseline and no unreconciled touched-but-undeclared
   components;
5. pass hard checks and the configured lifecycle, provenance, coverage, anchor,
   and required-update checks in the relevant scope;
6. present all remaining semantic-review clues before any write occurs.

The command prints a dry-run plan by default. `--confirm` applies the plan and
asserts that the caller has reviewed the semantic clues; it does not turn those
clues into deterministic facts. If mechanical blockers remain, `--confirm` cannot
override them.

### Confirmed semantic bindings

Component ownership can derive candidate component docs, but it cannot determine
which exact symbol satisfies a behavioral requirement. That relation is a semantic
judgment and must be confirmed.

For every `Provenance: code` requirement, finalization accepts one or more explicit
bindings:

```text
irminsul change finalize 0035-sso-login \
  --anchor sso-login=src/auth/oidc.py#OIDCClient.authenticate \
  --anchor sso-login=tests/test_oidc.py#test_valid_assertion \
  --confirm
```

The evidence report proposes changed symbols and related tests as candidates, but
does not select them silently. Agents can inspect the candidates and construct the
confirmed command after human authorization. Code and test anchors may both be
used: implementation anchors detect implementation movement, while test anchors
record executable scenario evidence.

This is the necessary limit on "derive, don't declare": derive every mechanically
knowable candidate and hash, but explicitly declare the semantic relationship that
code cannot infer.

### Promote requirements into component docs

For each confirmed requirement, finalization:

1. resolves candidate owners from the bindings and `affects`;
2. requires an explicit owner choice when more than one component is plausible;
3. writes the requirement's concise behavioral invariant into the canonical
   component doc as an anchored claim with stable id
   `<rfc-id>#<requirement-id>`;
4. records the RFC/ADR provenance and confirmed code/test anchors;
5. derives and writes anchor hashes using the existing anchor mechanism;
6. adds the component doc's `implements` backlink to the RFC;
7. checks `describes` coverage and proposes a separately confirmed ownership fix
   when new code is uncovered;
8. transitions the RFC to `implemented` only after every write succeeds.

Finalization does not silently extend `describes`: ownership is curated intent even
when candidate owners are mechanically discoverable.

Requirements backed only by an ADR or citation are promoted with that provenance
and no fabricated code anchor. An explicit no-new-behavior RFC finalizes through
its ADR, required updates, diff reconciliation, and checks without creating empty
claims.

### Canonical and historical copies

The implemented RFC remains an immutable historical record of the proposed change,
including its scenarios and implementation plan. Finalization does not copy those
sections verbatim into an explanation-oriented component doc. It promotes only the
concise live invariant, its provenance, and confirmed anchors; scenarios remain
historical acceptance context and may be represented by confirmed test evidence.

The promoted component claim is the canonical live statement. It carries a backlink
to the RFC but is the only copy evaluated for ongoing freshness. Later changes
update, replace, or retire the canonical claim and use the existing supersession
machinery to preserve history.

This does not violate SSOT: the RFC records what was proposed at that point in
history; the component claim records what the system currently promises.

### Idempotency and atomicity

Promoted claim ids make finalization idempotent. Re-running against an identical
implemented RFC produces no writes. A partial or conflicting promotion aborts
before changing `rfc_state`; all file mutations are presented together and use the
same dry-run/confirmation contract as `irminsul fix`.

The transition check enforces:

- only `accepted -> implemented` is valid;
- an implemented RFC has an ADR, Resolution section, explicit `affects`, and no
  unresolved promotion blockers;
- every code-backed requirement resolves to its canonical promoted claim;
- every promoted claim links back to the RFC and has valid confirmed evidence.

### What finalization proves

Finalization proves mechanically that:

- the RFC and promoted claims have valid structure and links;
- the declared and observed component scopes were reconciled;
- confirmed evidence symbols existed at the reviewed revision;
- current hashes match those reviewed symbols;
- required docs and ownership coverage are present.

It does **not** prove that the implementation semantically satisfies the
requirement. It makes that review explicit, grounded, and sensitive to later code
change.

## Drawbacks

- **Confirmed input is required.** Exact requirement-to-symbol relationships cannot
  be safely automated, so finalization needs agent or human review.
- **Multi-file writes.** Promotion, backlinks, anchors, and lifecycle transition
  require careful atomic planning and rollback on failure.
- **Anchor churn.** Implementation refactors intentionally trigger re-review even
  when external behavior is unchanged.
- **Historical migration.** Existing accepted-and-shipped RFCs need a verify and
  promotion pass before becoming `implemented`.

## Alternatives

- **Transition to implemented without promotion.** Rejected because it records a
  completion assertion without leaving durable evidence.
- **Automatically choose the nearest changed symbol.** Rejected because proximity
  does not establish semantic satisfaction.
- **Leave requirements only in implemented RFCs.** Rejected because evolution docs
  are historical; live behavioral claims belong with the component that owns them.
- **Automatically update ownership globs.** Rejected because component ownership is
  curated intent and an incorrect glob can hide coverage gaps.
- **Require code anchors for every requirement.** Rejected because ADR and external
  constraints have valid non-code provenance.

## Unresolved Questions

- Exact CLI syntax for multiple code and test anchors per requirement.
- Whether a requirement spanning components is split before finalization or may
  promote coordinated claims with one shared source id.
- How finalization records the semantic reviewer without creating identity or
  approval infrastructure.
- Transaction strategy for restoring multiple Markdown files after a failed write.

## Resolution

Implemented before 2026-07-15 and recorded by
[`ADR-0016`](../../50-decisions/0016-freeze-implemented-rfc-records.md).
