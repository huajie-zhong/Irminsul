---
id: 0042-rfc-dependency-and-supersession-graphs
title: "RFC dependency and supersession graphs"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
affects:
  - change
  - cli
---

# RFC 0042: RFC dependency and supersession graphs

## Summary

Add `irminsul change graph [<rfc>]` as a deterministic, read-only view of how
proposals depend on and supersede one another. Reuse the existing `depends_on`
and `supersedes` fields, derive reverse supersession edges, retain invalid edges
as evidence, and expose lifecycle-aware statuses, conflicts, and cycles to agents.

## Motivation

Irminsul records RFC state and generic document relationships, but an agent cannot
currently answer basic change-planning questions in one call: which proposals block
this one, what depends on it, whether a replacement is only planned or effective,
or whether the relationship set contains a cycle or competing successors.

Generic backlinks are not enough. They do not interpret lifecycle state, distinguish
dependency from replacement, or preserve dangling and non-RFC targets as explicit
problems. The existing generic supersession check also expects a reverse pointer on
the old document, which is incompatible with immutable implemented RFC records.

## Requirements

### Requirement: Reuse authored relationship fields
ID: reuse-authored-relations
Provenance: code

The graph MUST derive dependency edges from RFC `depends_on` entries and
supersession edges from the newer RFC's `supersedes` entries, without introducing
a second relationship schema.

#### Scenario: Forward supersession
- **WHEN** a new RFC lists an old RFC in `supersedes`
- **THEN** the graph derives both the forward replacement and reverse successor view without editing the old RFC

#### Scenario: Reverse pointer on an RFC
- **WHEN** an RFC carries `superseded_by`
- **THEN** the graph reports that legacy reverse declaration as an issue and does not treat it as an authoritative edge

### Requirement: Preserve incomplete evidence
ID: preserve-incomplete-evidence
Provenance: code

Every authored relationship from an RFC whose target is unresolved or references
the source itself MUST remain visible as incomplete evidence. A target that resolves
to a non-RFC document remains a valid generic document relationship and is excluded
from this RFC-specific graph without an issue.

#### Scenario: Dangling target
- **WHEN** a relationship names an unknown id
- **THEN** the edge remains in the report with `invalid` status and an `unknown-target` issue

#### Scenario: Generic document dependency
- **WHEN** `depends_on` resolves to a component, workflow, decision, or other non-RFC document
- **THEN** it is excluded from the RFC graph without being misreported as invalid

### Requirement: Interpret lifecycle without inferring it
ID: interpret-lifecycle-without-inference
Provenance: code

The graph MUST report canonical lifecycle state and MUST represent a missing state
as JSON `null`; it MUST NOT derive a state from status, prose, links, or code.

#### Scenario: Dependency state
- **WHEN** a dependency targets an implemented, active, rejected, or unclassified RFC
- **THEN** its status is respectively `satisfied`, `pending`, `blocked`, or `unknown`

#### Scenario: Rejected source
- **WHEN** the depending RFC is rejected
- **THEN** its dependency edge is `void` regardless of the target state

#### Scenario: Supersession state
- **WHEN** the superseding RFC is implemented, draft or accepted, rejected, or unclassified
- **THEN** its edge is respectively `effective`, `planned`, `void`, or `unknown`

### Requirement: Expose graph contradictions
ID: expose-graph-contradictions
Provenance: code

The report MUST deterministically identify self-reference, relation cycles, multiple
effective successors for one RFC, and an implemented RFC whose dependency is not
implemented. These are evidence issues in the query, not automatic lifecycle writes.

#### Scenario: Cycle
- **WHEN** two or more RFCs form a dependency or supersession cycle
- **THEN** a stable, relation-typed cycle component and per-problem issue are returned

#### Scenario: Competing successors
- **WHEN** multiple implemented RFCs supersede the same RFC
- **THEN** one issue identifies the target and every competing successor

#### Scenario: Implementation ordering contradiction
- **WHEN** an implemented RFC depends on an RFC that is not implemented
- **THEN** the graph reports an `implemented-before-dependency` issue

### Requirement: Support repository and focused queries
ID: support-repository-and-focused-queries
Provenance: code

`change graph` MUST return the repository RFC graph, while `change graph <rfc>`
MUST return the complete connected component around that RFC using the selected
relationship kinds in both directions.

#### Scenario: Relation filter
- **WHEN** `--relation dependency` or `--relation supersession` is selected
- **THEN** nodes, edges, cycles, and issues are limited to that relation

#### Scenario: Focused query
- **WHEN** one RFC is selected
- **THEN** every transitively connected predecessor and successor is included, plus the focus even when isolated

### Requirement: Provide stable agent output
ID: provide-stable-agent-output
Provenance: code

The command MUST support concise plain output and versioned JSON with deterministically
sorted nodes, edges, cycles, and issues. Relationship problems MUST NOT make this
read-only observability command exit nonzero.

#### Scenario: JSON query
- **WHEN** an agent requests `--format json`
- **THEN** version, focus, relation, nodes, edges, cycles, and issues are returned with stable typed fields

#### Scenario: Unknown focus
- **WHEN** the requested focus does not resolve to an RFC
- **THEN** the command exits as a usage error rather than returning an empty graph

## Detailed Design

`change/relations.py` owns a pure projection over `DocGraph`. An RFC is a document
under the configured `80-evolution/rfcs/` directory; the index is excluded. Nodes
carry id, path, title, document status, and canonical lifecycle state or JSON `null`.

Every edge carries relation, source, target, declaration path and line, and a
derived status. Unknown targets are retained rather than filtered; relationships
that resolve outside the RFC directory are generic document edges and do not enter
the RFC graph. Strongly
connected components provide deterministic cycle reporting without pretending one
arbitrary traversal is the canonical cycle path.

With no focus, all RFC nodes are returned so isolated proposals remain visible. A
focused query computes the undirected connected component over the selected typed
edges, while preserving their authored direction in output. `--relation all` is the
default.

This RFC adds observability first. A later decision may promote selected graph issues
into lifecycle gates, but query issues remain visible and non-blocking so an agent can
inspect a broken graph before deciding how to repair it.

## Tasks

- `T1` Add the typed relation projection, lifecycle statuses, and stable serialization. (component: change)
- `T2` Add cycle, conflict, invalid-target, and implementation-order analysis. (req: expose-graph-contradictions)
- `T3` Add `change graph` with full and focused plain/JSON modes. (component: cli)
- `T4` Add fixture coverage for valid, incomplete, cyclic, conflicting, and unclassified graphs. (component: change)
- `T5` Document the agent query and forward-only RFC supersession contract. (component: change)

## Drawbacks

- Reusing generic fields means their semantics depend on document kind; RFC graph
  consumers must apply the RFC-specific interpretation defined here.
- Full graph output includes isolated RFCs and can be large in mature repositories.
- Query-time issues expose contradictions but do not yet block transition or
  finalization.

## Alternatives

- Add `rfc_dependencies` and `rfc_supersedes` fields. Rejected because it creates
  parallel sources of truth for relationships already expressible in frontmatter.
- Materialize `superseded_by` on the old RFC. Rejected because implemented RFCs are
  frozen and reverse edges are mechanically derivable.
- Hide invalid edges. Rejected because absence would make a broken graph look clean.
- Infer lifecycle state for old RFCs. Rejected because relationship context does not
  establish human intent or approval.
- Make every graph issue a hard check immediately. Deferred until the read contract
  is exercised; observability should land before new repository gates.

## Unresolved Questions

- Which graph issues should later gate acceptance or implementation, and at which
  transition?
- Should MCP expose the same query after the CLI/JSON contract has stabilized?
