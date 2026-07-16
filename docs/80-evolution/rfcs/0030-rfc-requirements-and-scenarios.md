---
id: 0030-rfc-requirements-and-scenarios
title: "Requirements and scenarios as review contracts"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: implemented
affects:
- change
- checks
- docgraph
- frontmatter
resolved_by: docs/50-decisions/0016-freeze-implemented-rfc-records.md
required_updates: []
frozen_hash: "sha256:18a7a5d430b906ca367351966cdeab2de114c5e343a673179ad9aa77d1d7b645"
---

# RFC 0030: Requirements and scenarios as review contracts

## Summary

Add structured requirements and scenarios to behavior-changing RFCs. The
structure gives deterministic checks stable units to validate and gives agents
precise semantic-review targets; it does not claim that grammar can prove the
implementation correct.

Requirements are proportional rather than universal. An RFC that changes
observable behavior records requirements and scenarios. A refactor, documentation
change, or internal maintenance proposal may explicitly state that it has no new
behavioral requirements instead of inventing artificial ones.

Each requirement has a stable local id and an evidence obligation. At proposal
time, `Provenance: code` means "finalization must bind this requirement to code";
it is not evidence that the not-yet-written implementation already exists.

## Motivation

Component binding from [0029](0029-bound-change-loop.md) can establish where a
change was intended to land. It cannot express what the implementation must do.
Without stable behavioral promises, an agent can inspect changed files but has no
precise contract against which to review them, and implementation finalization has
nothing specific to promote into the owning component docs.

The value is therefore not the SHALL vocabulary itself. The value is a small,
parseable contract that connects:

`intent -> requirement -> scenario -> implementation evidence -> anchored claim`.

## Detailed Design

### Body shape

Behavior-changing RFCs use a `## Requirements` section:

```markdown
## Requirements

### Requirement: SSO login
ID: sso-login
Provenance: code

Users SHALL be able to authenticate through their company identity provider.

#### Scenario: Valid SSO assertion
- **WHEN** the identity provider returns a valid assertion
- **THEN** a session is established

#### Scenario: Expired SSO assertion
- **WHEN** the identity provider returns an expired assertion
- **THEN** authentication is rejected
```

`ID` is unique within the RFC and stable across wording changes. Its globally
addressable identity is `<rfc-id>#<requirement-id>`, for example
`0035-sso-login#sso-login`. Tasks in 0031 and promoted claims in 0032 use this id;
they do not match mutable heading text.

An RFC with no new behavioral contract writes an explicit disposition:

```markdown
## Requirements

No new behavioral requirements: this refactor preserves the existing contract.
```

This is reviewable intent, not an empty section or silent omission.

### Evidence obligations

`Provenance` reuses the project's three evidence classes:

- `code` - the requirement is expected to become an anchored code claim during
  implementation finalization;
- `adr` - the requirement is a decision constraint and must resolve through the
  RFC's ADR relationship;
- `citation` - the requirement comes from an external authority and must contain a
  resolvable link.

Before implementation, a code provenance is reported as `planned/unbound`. After
the RFC becomes `implemented`, the corresponding canonical claim must have a
confirmed code anchor or an explicit disposition explaining why code is not the
right evidence. This keeps provenance honest across the lifecycle.

### Deterministic grammar check

A soft-deterministic `requirement-grammar` check parses the RFC body and validates:

- requirement ids are present, syntactically valid, and unique within the RFC;
- every requirement contains SHALL or MUST behavior text;
- every requirement has at least one named scenario;
- every scenario contains a WHEN and THEN;
- provenance is one of the supported evidence classes;
- task and promoted-claim references resolve to a requirement id;
- an explicit no-new-behavior disposition is not mixed with requirement blocks.

Malformed draft RFCs produce warnings. `change transition ... accepted` treats
grammar findings as blockers because acceptance freezes the contract to implement.

Body-section parsing is new shared capability. It belongs in the graph's markdown
index rather than in ad hoc check regexes so requirement ids, task links, headings,
and source lines have one parser and one representation.

### Semantic-review clues

Grammar cannot determine whether a requirement is useful, complete, feasible, or
implemented. `change status` and `change verify` therefore emit clues for agent or
human review, including:

- a requirement has no negative or failure scenario;
- requirement wording is broader than the declared affected components;
- no related source or test changed;
- a scenario has implementation evidence but no test evidence;
- two requirements appear to make competing promises.

Deterministic clues are grounded in observable absence or mismatch. Optional LLM
advisory checks may interpret the requirement and code, but their conclusion never
enters the hard profile or silently changes lifecycle state.

### Proportional adoption

The transition check does not require behavior blocks merely because
`affects` is non-empty. Instead, it requires either one or more well-formed
requirements or the explicit no-new-behavior disposition. The reviewer decides
whether that disposition is credible; Irminsul makes the decision visible.

## Drawbacks

- **Authoring cost.** Behavioral changes require concrete scenarios before
  implementation; this is intentional design pressure but should not burden
  maintenance-only RFCs.
- **New parser surface.** Structured body sections become a first-class DocGraph
  concept and require line-accurate tests.
- **False confidence.** A green grammar check proves structure only. The command
  output must keep mechanical readiness and semantic review visibly separate.
- **Stable ids.** Requirement ids add a small amount of authored identity, but are
  necessary for tasks, promotion, and supersession to survive heading edits.

## Alternatives

- **Requirements in frontmatter.** Rejected because multiline behavioral intent
  belongs in prose and would make canonical metadata difficult to review.
- **Free-form acceptance criteria.** Easier to write, but tasks and finalization
  cannot reference stable units and deterministic structure checks become brittle.
- **Require scenarios for every RFC.** Rejected because it creates ceremony and
  synthetic contracts for refactors and documentation-only changes.
- **Treat code provenance as current proof at proposal time.** Rejected because the
  implementation may not exist; it is an evidence obligation until finalization.

## Unresolved Questions

- Exact requirement-id syntax and whether ids may be reused by a superseding RFC.
- Whether GIVEN is supported as an optional scenario keyword.
- Whether the explicit no-new-behavior disposition needs a structured marker or a
  canonical sentence recognized by the parser.

## Resolution

Implemented before 2026-07-15 and recorded by
[`ADR-0016`](../../50-decisions/0016-freeze-implemented-rfc-records.md).
