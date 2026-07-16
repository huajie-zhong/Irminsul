---
id: 0038-context-content-excerpts
title: "Deterministic content excerpts in context packets"
audience: explanation
tier: 2
status: draft
depends_on:
  - 0037-workflow-context-modes
describes: []
rfc_state: draft
affects:
  - cli
  - context
---

# RFC 0038: Deterministic content excerpts in context packets

## Summary

Make context packets useful without an immediate second file-read round trip.
Workflow context includes bounded excerpts from the owning document, its
structured claims, and requirements in explicitly affecting active RFCs.
`--include` lets a caller select those categories or expand direct dependency
documents using the same deterministic rules.

This RFC defines extraction and fixed output bounds only. It does not introduce
weighted relevance, token budgets, semantic search, or interactive expansion.
It is the explicit content-selection extension deferred by RFC 0037.

## Motivation

The context command currently answers "which file should I read?" but not "what
does that file say that matters before this edit?" An agent must parse the
metadata, issue more reads, rediscover the relevant section, and only then start
work. That adds latency and makes it easy to skip the repository's actual
invariants.

Returning whole documents creates the opposite failure: a component with many
dependencies or a large RFC can flood the packet. The first content layer should
therefore be predictable and bounded before a later ranking RFC considers token
budgets or weighted selection.

## Requirements

### Requirement: Include owner content by default
ID: include-owner-content
Provenance: code

Workflow context MUST include a bounded introductory excerpt from each owning
document and MUST identify the source, category, and deterministic reason for
including it.

#### Scenario: Owner has introductory prose
- **WHEN** a before-edit or after-edit result resolves to an owning document
- **THEN** the packet includes the first substantive prose block under its first applicable heading

#### Scenario: Ordinary context lookup
- **WHEN** a caller uses a primitive path, topic, or changed lookup without `--include`
- **THEN** its existing JSON shape remains unchanged

### Requirement: Include explicit invariants
ID: include-explicit-invariants
Provenance: code

Workflow context MUST include structured owner claims and parsed requirement
prose from active RFCs that explicitly affect the owner, subject to fixed count
and excerpt bounds.

#### Scenario: Active RFC has requirements
- **WHEN** an active RFC is included through its explicit `affects` relationship
- **THEN** requirement prose is copied from the existing parsed requirement index with its id and title

#### Scenario: Owner has structured claims
- **WHEN** the owner declares frontmatter claims
- **THEN** their authored claim text is included as explicit invariants rather than inferred from arbitrary prose

### Requirement: Expand categories explicitly
ID: expand-content-categories
Provenance: code

`context --include <categories>` MUST accept a deterministic comma-separated
selection of `owner`, `claims`, `requirements`, and `dependencies`, plus `all`
and `none`, and MUST reject unknown categories.

#### Scenario: Dependencies requested
- **WHEN** `dependencies` is included
- **THEN** introductory excerpts from directly declared `depends_on` documents are added in stable path order

#### Scenario: Category exceeds its bound
- **WHEN** eligible excerpts exceed the fixed per-result or per-excerpt limits
- **THEN** the response reports omitted counts and truncation explicitly instead of silently dumping or ranking content

## Detailed Design

Content selection remains separate from workflow stage and lookup mode. Workflow
aliases default to `owner,claims,requirements`; primitive context calls default
to no content for compatibility but accept the same `--include` option.

Each serialized excerpt carries `category`, `doc_id`, `path`, `title`, `text`,
`reason`, and `truncated`. Owner and dependency excerpts use the first substantive
Markdown prose under the first applicable heading, excluding the heading itself.
Claim excerpts use structured `claims[].claim`; requirement excerpts use the
parsed requirement text already indexed on the DocGraph.

Selection order is fixed: owner, claims in authored order, active RFCs by path
with requirements in authored order, then dependencies by path. Each excerpt is
limited to 20 lines and 1,200 characters. Each result includes at most eight
excerpts. The response reports how many eligible excerpts in each category were
omitted after that limit. These are protocol constants, not configurable weights
or token estimates.

The JSON result gains a `content` object only when content was requested or
selected by a workflow default. Plain output renders the same excerpts and
omission counts. Source documents are never modified.

## Tasks

- `T1` Add deterministic Markdown, claim, and requirement excerpt extraction. (component: context)
- `T2` Add bounded content serialization and plain formatting with omission counts. (component: context)
- `T3` Add validated `--include` category selection and workflow defaults. (component: cli)
- `T4` Document compatibility, bounds, and the deferred ranking boundary. (component: context)

## Drawbacks

- The introductory section is a structural heuristic, not a semantic match for
  the edited symbol. Authors still need well-factored component docs.
- Fixed limits may omit a relevant later requirement. The packet reports the
  omission, but choosing which item is most relevant belongs to the ranking RFC.
- Including content increases response size compared with A6's metadata-only
  workflow packet.

## Alternatives

- Return complete related files. Rejected because output grows without a useful
  bound and repeats content the agent may not need.
- Use embeddings or an LLM to select passages. Rejected because Irminsul's query
  contract is deterministic and offline.
- Add token budgets and relationship weights now. Deferred because stable
  scoring, cost estimation, tie-breaking, and explainability need their own RFC.

## Unresolved Questions

- A later RFC must decide whether anchor-aware selection should precede or feed
  weighted ranking.
- The fixed bounds should be evaluated against real repositories before any
  compatibility promise makes them configurable.
