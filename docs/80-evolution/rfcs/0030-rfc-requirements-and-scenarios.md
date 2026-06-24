---
id: 0030-rfc-requirements-and-scenarios
title: "Requirements and scenarios in the RFC, with provenance"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0030: Requirements and scenarios in the RFC

## Summary

Iteration 2 of the [bound-change loop](0029-bound-change-loop.md). Give a change a
structured **requirements** section in the RFC *body* (not frontmatter), each
requirement an EARS-style statement (`SHALL`/`MUST`) with at least one
`#### Scenario:` block, and each carrying **provenance** (code / ADR / citation)
per Principle 2 ([`principles.md`](../../00-foundation/principles.md)). A
deterministic grammar check validates the structure — reaching parity with the
internal-consistency guarantee spec-driven tools provide — while provenance keeps
each requirement *bound*, which those tools do not.

## Motivation

Iteration 1 binds a change at the component level. Real proposals promise specific
*behaviors*, and behaviors are the unit reviewers and agents actually reason about.
Spec-driven tools already model this well: a requirement is a SHALL statement with
named scenarios, and a validator enforces that shape. irminsul should match that
authoring rigor — agents produce far better implementations from a scenario list
than from a paragraph — but without inheriting the unbound-spec rot: a requirement
must trace to evidence, not float.

Requirements also become the anchor targets for iteration 4
([`0032`](0032-accept-time-anchoring.md)), where they fold into the owning
component doc as pinned claims. So this RFC defines the artifact that later gets
bound; here it only has to exist and be well-formed.

## Detailed Design

### Body shape

Requirements live in a `## Requirements` section of the RFC body, mirroring the
markdown-body placement spec tools use (keeping frontmatter lean per the
derive-don't-declare law of [`0029`](0029-bound-change-loop.md)):

```markdown
## Requirements

### Requirement: SSO login
Users SHALL be able to authenticate via SSO.
Provenance: code

#### Scenario: Valid SSO assertion
- **WHEN** the IdP returns a valid assertion
- **THEN** a session is established
```

### Grammar check (parity)

A soft-deterministic check, `requirement-grammar`, validates each requirement in a
change RFC:

- a `### Requirement:` block has SHALL/MUST text and **at least one**
  `#### Scenario:` block;
- scenarios use level-4 headers (not bare bullet lists);
- requirement names are unique within the RFC.

These mirror the structural rules a spec validator enforces, so a change RFC is
held to the same internal-consistency bar.

### Provenance (the binding)

Each requirement declares `Provenance: code | adr | citation`, reusing the
structured-claim provenance model of
[`0010-structured-claim-provenance`](0010-structured-claim-provenance.md):

- `code` — the requirement is satisfied by source; it becomes anchorable to that
  source in 0032 via the [`anchors`](../../20-components/anchors.md) mechanism.
- `adr` — the requirement records a decision; it must resolve to an ADR (the same
  linkage [`0017-rfc-resolution-check`](0017-rfc-resolution-check.md) already
  validates for the RFC itself).
- `citation` — an external authority; an external link the
  `external-links` check can reach.

A requirement with `Provenance: code` is *not yet* required to name the exact
symbol here — that pinning is the job of accept-time anchoring (0032). At this
iteration the check only verifies the provenance *kind* is present and internally
plausible (an `adr` provenance resolves, a `citation` is a real link).

### Relationship to spec-driven tools

This is the deliberate parity step. A spec tool's requirement (`### Requirement` +
`#### Scenario`) and its grammar validator are reproduced here almost verbatim —
the format is good and worth adopting. The single addition is the `Provenance:`
line, which is what later lets the requirement be *bound* to code rather than left
as a durable-but-unverified spec entry.

## Drawbacks

- **Author effort.** Scenarios are more work than a paragraph; mitigated because
  agents, the primary consumers, both write and benefit from them.
- **Grammar strictness.** Like any structural validator, `requirement-grammar` will
  reject loosely-written requirements; that is the intended pressure.
- **Provenance ahead of anchoring.** Declaring `Provenance: code` before 0032 lands
  is a promise the engine cannot yet fully verify; until then it is checked only
  for presence and kind.

## Alternatives

- **Requirements in frontmatter** — rejected: bloats metadata and fights the
  lean-frontmatter law of 0029; body prose is the right home and matches spec-tool
  convention.
- **No provenance, grammar only** — rejected: that is exactly the unbound spec that
  rots; provenance is the differentiator.
- **A separate `requirements/` file per change** — rejected: re-introduces a
  parallel tree; the RFC body is sufficient and keeps one home per change.

## Unresolved Questions

- Whether `requirement-grammar` is a distinct check or an extension of an existing
  one.
- Exact provenance syntax (`Provenance:` line vs. a structured claim block reusing
  0010's machinery directly).
- Whether scenario keywords (`WHEN`/`THEN`/`AND`) are enforced or merely
  conventional.
