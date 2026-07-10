---
id: 0033-derived-layered-impact
title: "Derived change impact and semantic-review clues"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0033: Derived change impact and semantic-review clues

## Summary

Add `irminsul change impact <id>` as a derived view over the diff and
[`DocGraph`](../../20-components/docgraph.md). It tells reviewers and agents where
a change reached, which existing checks govern those areas, and which semantic
questions remain. Impact is recomputed on demand and never stored as an RFC
footprint.

The command is useful at three points: feasibility review while an RFC is draft,
implementation orientation after acceptance, and scope reconciliation before
finalization. It is an evidence and routing surface, not a second enforcement
engine.

## Motivation

A component-level `affects` declaration states intended scope, but significant
changes can also alter architecture, public surfaces, workflows, terminology, and
foundation assumptions. Reviewers currently have to invoke several commands and
reconstruct that ripple themselves.

The layered graph is specifically well suited to providing those clues. A compact
impact report answers:

- How broad should the review be?
- Which docs and checks should the agent inspect next?
- Did the implementation expand beyond the accepted plan?
- Which observations are mechanical, and which require semantic judgment?

## Detailed Design

### Inputs and phases

`irminsul change impact <id> [--base-ref REF]` supports two evidence levels:

- **plan impact** - available without a diff; uses `affects`, `direction`,
  requirements, dependencies, and graph links to identify intended review areas;
- **observed impact** - available with a working-tree or base-ref diff; adds actual
  owners, changed docs, test evidence, and surface deltas.

The output states which level it used. A missing baseline never renders as an empty
observed impact.

### Derived observations by layer

The report gathers only facts existing machinery can support:

- **Foundation (00).** `direction: revises` creates a foundation-review clue and
  lists foundation docs linked from the RFC. Irminsul does not infer which
  principle code semantically violates.
- **Architecture (10).** New, removed, or moved component docs; parent-child
  changes; architecture docs changed in the diff; and existing hierarchy or
  phantom-layer findings.
- **Components (20).** Declared affected components, diff-derived owners, scope
  divergence, unowned source, related tests, and component findings.
- **Workflows (30).** Workflow docs linked to or dependent on affected components,
  plus workflow docs actually changed. A link is a review route, not proof that the
  workflow behavior changed.
- **Decisions (50).** The RFC's ADR, unresolved required updates, and decision
  backlinks.
- **Evolution (80).** Superseded or related RFCs and claims that may need promotion
  or retirement.
- **Surfaces.** Added, removed, or changed CLI, HTTP, export, environment-variable,
  and configured inventory identities from the existing surface extractors.
- **Glossary.** Existing glossary-discipline findings and candidate terms from the
  RFC or changed docs; agents decide whether a candidate is truly a domain term.

Every observation includes its source: declared RFC field, diff path, graph edge,
surface extractor, or finding id.

### Review clues, not semantic findings

The report converts mechanical observations into grounded questions:

```text
Observed: CLI surface added `login --sso` under component `auth`.
Review: Does the accepted RFC describe this public behavior and its failure cases?

Observed: `billing` changed but is absent from `affects`.
Review: Is this an intended scope expansion or an accidental side effect?

Observed: direction is `revises`; no foundation doc changed.
Review: Does the implementation revise a project principle, and if so which one?
```

These clues are included in CLI JSON and MCP output for an agent to inspect. An
optional advisory LLM check may answer or refine them, but its result remains
advisory. Deterministic checks only enforce the underlying structural facts.

### Integration with the lifecycle

Impact is not a fifth disconnected report:

- `change status` includes a terse impact summary and next review routes;
- `change verify` includes full observed impact and scope-divergence clues;
- `change finalize` blocks only on mechanical impact problems such as unowned code
  or unreconciled touched-but-undeclared components;
- `context --change` links to the same report instead of reproducing its logic.

### Impact altitude

Output defaults to the highest layer with actual evidence plus the components and
surfaces involved. A component-only change remains compact. `--all-layers` includes
empty sections for automation or exhaustive review.

## Drawbacks

- **Git baseline dependency.** Observed impact needs an explicit or discoverable
  change range; plan impact is necessarily less precise.
- **Graph-edge limits.** A linked workflow is a candidate review route, not proof
  of behavioral impact.
- **Agent review cost.** Broad changes may produce many clues; source attribution
  and impact altitude are required to keep the report actionable.
- **Extractor coverage.** Public surfaces without configured extractors remain
  invisible until the project adds one.

## Alternatives

- **Store an `impact:` block on the RFC.** Rejected because owners, surfaces, and
  changed paths are derivable and would immediately become stale metadata.
- **Report only affected files.** Rejected because it loses graph ownership,
  lifecycle, and layer-specific review routes.
- **Make every clue a check finding.** Rejected because questions such as whether a
  principle changed are semantic; the tool should expose evidence without
  pretending to know the answer.
- **Run impact only at finalization.** Rejected because draft feasibility and
  accepted implementation orientation are two of its highest-value uses.

## Unresolved Questions

- Configuration of default impact altitude and maximum clue count.
- Whether candidate glossary terms come from a deterministic tokenizer or only
  existing glossary findings in the first iteration.
- How to represent source attribution compactly in plain output while preserving
  complete JSON evidence.
