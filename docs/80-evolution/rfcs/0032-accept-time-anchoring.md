---
id: 0032-accept-time-anchoring
title: "Accept-time anchoring: archive that anchors, not just tidies"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0032: Accept-time anchoring

## Summary

Iteration 4 of the [bound-change loop](0029-bound-change-loop.md), and the step
where the loop overtakes a plain spec tool. When a change is accepted, its
[requirements](0030-rfc-requirements-and-scenarios.md) are **folded into the owning
component docs as anchored claims** — pinned to the code that satisfies them via the
[`anchors`](../../20-components/anchors.md) mechanism — the affected component's
`describes:` mapping is updated, and the ADR linkage is recorded. A spec tool's
archive *tidies* a canonical spec; this archive *anchors*, leaving behind claims the
engine keeps true forever.

## Motivation

In a spec tool, archiving merges a change's deltas into a canonical spec tree and
stops. The merged requirement is durable but unbound: nothing afterwards checks the
code still does what it says. That is the rot the project exists to kill
([`principles.md`](../../00-foundation/principles.md)).

irminsul already has every piece needed to do better: anchored prose claims that pin
a paragraph to a code symbol and flag drift
([`0024-anchored-prose-claims`](0024-anchored-prose-claims.md)), structured claim
provenance ([`0010-structured-claim-provenance`](0010-structured-claim-provenance.md)),
RFC→ADR resolution ([`0017-rfc-resolution-check`](0017-rfc-resolution-check.md)),
and component `describes:` coverage. Accept-time anchoring is the act of running
these at the moment a change lands, so a requirement becomes a *permanent, checked
obligation on the right component doc* instead of a line in an unwatched spec.

## Detailed Design

### What acceptance does

When an RFC moves to `rfc_state: accepted` (the existing lifecycle transition), an
`irminsul fix`-style remediation
([`0022-universal-fix-coverage`](0022-universal-fix-coverage.md)) performs, per
requirement:

1. **Resolve the owner.** Use the change's `affects` plus the diff→owner derivation
   to find the component doc that owns the satisfying code.
2. **Fold the requirement in.** Write the requirement (statement + scenarios) into
   that component doc as a claim, not a copy of derivable facts — the prose states
   the *behavior* (non-derivable), and the binding is the anchor.
3. **Anchor `Provenance: code` requirements.** Pin the claim to its satisfying
   symbol via `anchors`, so later code change to that symbol raises a re-pin flag —
   the freshness signal a spec tool has no equivalent for.
4. **Update `describes:`.** Ensure the component's globs cover the new code (the
   iteration-1 `change-binding` check now passes for real, not just by declaration).
5. **Record the decision.** Confirm the RFC's `resolved_by` ADR exists, reusing the
   rfc-resolution check.

### After acceptance

The change RFC is resolved; the *binding* it created lives on in the component
graph. Every later run of coverage, `claim-anchor`, and co-change
([`0021-code-doc-cochange`](0021-code-doc-cochange.md)) now watches the folded
requirement. The proposal is gone; its guarantee is permanent.

### Relationship to OpenSpec

This is the divergence point. Where a spec tool's archive produces a tidy but
unverified canonical spec, accept-time anchoring produces a fully-connected,
code-pinned subgraph: intent → ADR → requirement → anchored claim → code →
component. Same trigger ("the change is done"), categorically stronger residue.

## Drawbacks

- **Remediation complexity.** Folding requirements into the correct component doc
  and anchoring them is the heaviest mechanical step in the stack; it must be
  idempotent and reversible like the rest of `fix`.
- **Owner ambiguity.** A requirement spanning multiple components needs a split or a
  primary-owner rule; see Unresolved Questions.
- **Anchor churn.** Anchored `code` requirements inherit the re-pin noise of
  [`0024`](0024-anchored-prose-claims.md) — accepted by design as the cost of
  freshness.

## Alternatives

- **Merge into a canonical spec tree** (the spec-tool archive) — rejected: produces
  the unbound, un-rechecked spec this whole stack exists to avoid.
- **Leave requirements in the resolved RFC** — rejected: RFCs are evolution-layer
  history; live behavioral claims belong on the component doc that owns the code, per
  SSOT (Law 1, [`laws.md`](../../00-foundation/laws.md)).
- **Manual fold** — rejected: a step that depends on human diligence will be skipped;
  the loop must mechanize it.

## Unresolved Questions

- Primary-owner rule for a requirement that spans components.
- Whether folding is automatic on the accept transition or an explicit
  `irminsul fix` target the agent runs.
- How a superseding change updates or retires a previously folded requirement
  (interplay with `supersedes` and the supersession check).
