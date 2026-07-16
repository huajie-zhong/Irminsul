---
id: 0037-workflow-context-modes
title: "Workflow-oriented context modes"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
affects:
  - cli
  - context
  - orient
---

# RFC 0037: Workflow-oriented context modes

## Summary

Add two stateless workflow aliases to the existing context command:
`irminsul context --before-edit <path...>` packages the deterministic knowledge
needed before changing one or more paths, while `irminsul context --after-edit`
packages the impact and validation of the current working-tree changes.

Workflow modes orchestrate existing capabilities. They introduce minimal new
repository semantics: ownership, relationships, lifecycle state, tests, and
findings continue to come from the current DocGraph and registered checks.

## Motivation

The current happy path asks an agent to translate an editing session into product
vocabulary: call `context` for a path, read the returned files, edit, call
`context --changed`, then run a hard check. Agents and new contributors instead
think in two intents: "give me what I need before I edit" and "tell me what this
edit affected and broke."

The primitive commands remain useful power tools, but the common loop should not
require every operator to learn their ordering before making a safe change.

## Requirements

### Requirement: Package pre-edit context
ID: package-pre-edit-context
Provenance: code

`context --before-edit` MUST accept one or more repository paths, build the graph
and run the selected checks once, group paths by their deterministic owner, and
report declared tests plus active RFCs whose `affects` list names that owner.

#### Scenario: Multiple paths share an owner
- **WHEN** an agent requests context for multiple paths owned by one component
- **THEN** the response contains one component result with every input path and matching claim

#### Scenario: Active RFC affects the owner
- **WHEN** a draft or accepted RFC explicitly names the owning component in `affects`
- **THEN** the response identifies the RFC, its state, and its parsed requirement ids without inferring a relationship from prose

### Requirement: Validate post-edit impact
ID: validate-post-edit-impact
Provenance: code

`context --after-edit` MUST inspect the same staged, unstaged, and untracked paths
as `context --changed`, run configured hard checks even when no changed path has
an owner, and report whether the repository passes the hard gate.

#### Scenario: Changed source has an owner
- **WHEN** a changed source path resolves to a component
- **THEN** the response reports the owner, declared tests, active RFCs, scoped findings, and whether its doc changed too

#### Scenario: Declared test changes
- **WHEN** a changed path is explicitly listed in one or more component `tests` fields
- **THEN** the response routes that path to those components instead of labeling it undocumented

#### Scenario: Hard finding is outside an owned result
- **WHEN** a configured hard check reports an error that is not scoped to an owned changed path
- **THEN** the workflow-level validation still reports that the hard gate failed

### Requirement: Emit deterministic next actions
ID: emit-deterministic-next-actions
Provenance: code

Workflow responses MUST emit ordered command-and-reason next actions derived
from explicit report state. They MUST be stateless and non-interactive, and MUST
not add ranking, token budgeting, excerpt selection, or hidden session state.

#### Scenario: Active change is present
- **WHEN** a workflow result includes an active RFC
- **THEN** a next action points to `irminsul change status <id>` and explains the explicit `affects` relationship

#### Scenario: Post-edit validation fails
- **WHEN** the configured hard gate has an error
- **THEN** a next action points to `irminsul check --profile hard`

## Detailed Design

Lookup mode and workflow stage remain separate. `mode` continues to be `path`,
`topic`, or `changed`; workflow responses add `workflow: before-edit|after-edit`,
`validation`, and `next_actions` to the versioned JSON report. Calls without a
workflow flag retain their existing JSON shape.

`--before-edit` uses the path resolver repeatedly against one graph. Results with
the same owner are merged deterministically. `--after-edit` is an intent alias for
changed-path lookup plus repository-level hard validation; it does not save a
before-edit snapshot or guess what an agent intended to change.

Workflow aliases default to the hard finding profile because hard validation is
their promised contract and they are expected to run frequently. Callers can opt
into `--profile configured` or `--profile all-available` for the broader audit;
ordinary context lookups retain their existing configured-profile default.

An active change is an RFC whose canonical state is `draft` or `accepted` and
whose explicit `affects` list contains the owning document id. Requirement ids
and titles come from the existing parsed requirements index. This version does
not search prose for implied impact or treat historical implemented/rejected RFCs
as active work.

Plain output leads with the workflow stage, retains the existing owner blocks,
and ends with validation and next actions. JSON keeps ordered arrays and explicit
reasons so an agent can act without parsing presentation text.

## Tasks

- `T1` Add multi-path context aggregation and active-change metadata. (component: context)
- `T2` Add the before-edit and after-edit CLI aliases with strict combination rules. (component: cli)
- `T3` Add workflow validation, deterministic next actions, and versioned JSON/plain output. (req: emit-deterministic-next-actions)
- `T4` Document the intended edit loop without hiding the existing power tools. (component: context)
- `T5` Teach the workflow aliases first in the orientation command vocabulary. (component: orient)

## Drawbacks

- The packet remains metadata-first until a separate content-expansion RFC adds
  excerpts. Agents may still need file reads after the initial call.
- Explicit `affects` links favor explainability over recall; an RFC with stale or
  missing scope will not appear as active context.
- Running configured checks makes the aliases more expensive than a bare metadata
  lookup, though graph construction and checks occur only once per invocation.

## Alternatives

- Replace the primitive commands with only workflow commands. Rejected because
  lifecycle transitions, focused queries, and debugging still need power tools.
- Start an interactive edit session. Rejected because agents integrate more
  reliably with explicit stateless commands and structured output.
- Add excerpts, weighted ranking, and token budgets now. Deferred to separate
  RFCs because they change retrieval and output-selection semantics.

## Unresolved Questions

- A later content-expansion RFC must define excerpt boundaries and output limits.
- A later ranking RFC must define stable weights, tie-breaking, token estimation,
  and selection explainability without changing this workflow-stage contract.
