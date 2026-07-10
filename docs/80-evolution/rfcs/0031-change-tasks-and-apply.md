---
id: 0031-change-tasks-and-apply
title: "Change tasks and implementation evidence"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0031: Change tasks and implementation evidence

## Summary

Give an RFC a static implementation task list and add a change-aware context view
that gathers mechanical evidence around those tasks. Irminsul does not implement
the tasks and does not claim to derive semantic completion from a diff. It gives an
agent the plan, relevant code, tests, docs, and mismatches needed to assess progress
without storing a separate progress model.

The distinction is deliberate:

- the RFC stores **what was planned**;
- Irminsul derives **what repository evidence now exists**;
- an agent or human judges **what is actually complete**.

## Motivation

An accepted RFC currently leaves an agent to reconstruct an implementation plan
from prose, find the relevant code, and decide what to do next. `context --changed`
already resolves changed files to owners, tests, dependencies, and findings, but it
does not organize that evidence around an RFC's requirements and tasks.

A bounded task list is useful change context, not a general project tracker. It
becomes a project tracker only if it accumulates assignees, deadlines, priorities,
sprints, or status fields unrelated to repository evidence. This RFC explicitly
excludes those features.

## Detailed Design

### Static task shape

Tasks live in the RFC body and have stable local ids. They are ordinary list items,
not mutable status records:

```markdown
## Tasks

- `T1` Wire the OIDC client. (req: sso-login)
- `T2` Add expired-assertion coverage. (req: sso-login)
- `T3` Document the SSO_ISSUER_URL environment variable. (req: sso-login)
```

The task list records the accepted implementation plan. It is not rewritten to
store a percentage, owner, timestamp, or inferred state. Tasks that implement a
behavioral requirement reference its stable id from 0030. A maintenance RFC with
an explicit no-new-behavior disposition may instead reference an affected
component: `(component: docgraph)`.

Task ids must be unique within the RFC. References must resolve to a requirement or
declared affected component. A task may be revised while the RFC is `draft` or
`accepted`; it freezes when the RFC becomes `implemented`.

### Change-aware evidence view

Add `irminsul change status <id>` and allow `context --change <id>` to present the
same report. For each requirement and its tasks, the deterministic layer gathers:

- changed source files owned by declared affected components;
- changed tests named by those component docs;
- changed documentation and required-update findings;
- public-surface additions or removals from 0033;
- hard and configured findings scoped to the changed files;
- whether no evidence could be associated with the task's requirement or component.

The report uses evidence labels, not completion labels:

```text
T1 Wire the OIDC client
  source evidence: src/auth/oidc.py
  test evidence:   none
  review clue:     inspect implementation and add or identify scenario coverage

T2 Add expired-assertion coverage
  source evidence: src/auth/oidc.py
  test evidence:   tests/test_oidc.py
  review clue:     confirm the expired assertion scenario is asserted
```

Summary counts are named precisely: `3/5 tasks with source evidence` or
`2/4 requirements with test evidence`, never `60% complete`.

### Agent semantic assessment

The JSON report gives agents task text, requirement text, scenarios, evidence
paths, relevant symbols when available, and review clues. An agent may use those
clues to present an advisory progress estimate or identify the next likely task.
That estimate is semantic output from the agent; Irminsul does not persist it and
does not use it as a deterministic lifecycle condition.

`change verify` may require explicit confirmation that the task plan was reviewed,
but finalization is governed by requirements and durable claims, not by guessing
that every original implementation step remained necessary. An accepted plan may
evolve as long as the RFC records material scope changes before finalization.

### No implementation executor

Irminsul does not write application code. The implementation loop is:

1. agent runs `change status` or `context --change`;
2. agent inspects the evidence and chooses the next task;
3. agent edits code/tests/docs;
4. agent reruns the report and deterministic checks;
5. agent runs `change verify` when it believes the requirements are satisfied.

This extends the existing
[`agent-protocol`](../../90-meta/agent-protocol.md) with RFC-specific orientation;
it does not add an autonomous executor.

## Drawbacks

- **No deterministic completion bar.** This is a correctness constraint, not a
  missing feature: changed files do not prove a free-text task is complete.
- **Coarse evidence.** Several tasks may share one requirement and therefore the
  same changed files; the agent still has to inspect semantics.
- **Plan evolution.** A static task list can become outdated during implementation;
  material changes must update the accepted RFC rather than creating hidden work.
- **Multi-PR baselines.** A long-running change needs an explicit base ref or CI
  change range to gather complete evidence.

## Alternatives

- **Checkboxes as canonical progress.** Reliable when maintained, but they make the
  RFC carry live execution state and still do not prove semantic completion.
- **Infer completion from changed code.** Rejected because touching an owning
  component is evidence, not proof that a task or scenario is satisfied.
- **Store status in a sidecar or frontmatter.** Rejected as a second source of truth
  with no stronger evidence than the repository already provides.
- **Add assignees, dates, or priorities.** Rejected; external issue trackers own
  coordination metadata. The RFC owns only the implementation plan.

## Unresolved Questions

- Whether task ids use `T1` syntax or slug ids matching requirements.
- Whether `context --change` aliases `change status` or one command becomes the
  canonical surface.
- How a multi-PR implementation supplies and preserves its complete comparison
  range without committing a stale file list.
