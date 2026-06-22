---
id: 0031-change-tasks-and-apply
title: "Change tasks and the apply loop"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0031: Change tasks and the apply loop

## Summary

Iteration 3 of the [bound-change loop](0029-bound-change-loop.md). Give a change a
**tasks** checklist in the RFC body and a way to track progress through
implementation, so the loop has an explicit *implement* phase — the analogue of a
spec tool's "apply" step — driven through the surfaces irminsul already has
([`context`](../../20-components/context.md),
[`cli`](../../20-components/cli.md)). Tasks are derivable progress, not new
governance: their state is read from the checklist and the diff, never maintained
as a second source of truth.

## Motivation

Iterations 1–2 produce a bound proposal with requirements. Implementation is still
unstructured: an agent reads the RFC and starts coding with no shared checklist, no
progress signal, and no link from "task done" back to "requirement satisfied."
Spec tools close this with an apply step that walks a `tasks.md` checklist; the
ergonomics genuinely help agents stay on track and let a human see where a change
stands. irminsul should offer the same, wired to its existing context command so
the agent's "what do I do next" question is answered from the live repo state.

## Detailed Design

### Body shape

A `## Tasks` section, one checkbox per task, optionally tagged with the requirement
it advances:

```markdown
## Tasks

- [ ] Wire the OIDC client  (req: SSO login)
- [ ] Add silent session refresh  (req: Session refresh)
- [ ] Document the SSO_ISSUER_URL env var
```

### Progress is derived, not stored

There is no separate progress file. `irminsul context --changed` already reports
ownership, tests, dependencies, and findings for the current edits
([`0011-agent-context-command`](0011-agent-context-command.md)); it gains a
**change view**: given the active change RFC, it surfaces the task list, marks tasks
whose `(req: …)` requirement now has satisfying code under the affected component
(reusing the diff→owner derivation of
[`0021-code-doc-cochange`](0021-code-doc-cochange.md)), and names the next open
task. Checkbox state in the RFC is the author's intent; the derived view is the
reality check against the diff. Where they disagree, the disagreement is the signal.

### No new "apply" executor

irminsul does not run the implementation — agents do. The "apply loop" is therefore
not a command that writes code; it is the context surface above plus the
[`agent-protocol`](../../90-meta/agent-protocol.md) work order, which already tells
an agent to locate context, implement, and run checks. This RFC adds the change-task
view to that loop; it does not add an autonomous executor.

### Relationship to OpenSpec

This reaches apply-step parity: a checklist the agent works through, with progress
visible. The difference is that progress is *derived from the diff against bound
components*, so "task done" can be cross-checked against "code actually changed
under the owning component," rather than trusting a checkbox.

## Drawbacks

- **Checkbox drift.** Authors may tick tasks the code does not support; mitigated
  by the derived reality view, but the checkbox itself remains advisory.
- **Requirement-tag optionality.** Tasks without a `(req: …)` tag cannot be
  cross-checked and fall back to plain checklist behavior.
- **Scope creep risk.** Tasks invite turning the RFC into a project tracker; kept
  in check by keeping tasks derivable-progress only, with no status metadata.

## Alternatives

- **A dedicated `tasks.md` per change** — rejected: a parallel file re-introduces a
  second tree; the RFC body holds tasks alongside the requirements they serve.
- **Stored task status** (in frontmatter or a sidecar) — rejected: violates
  derive-don't-declare; progress is read from the diff and checklist on demand.
- **An autonomous `apply` command** — out of scope: irminsul governs, it does not
  implement; the agent remains the executor.

## Unresolved Questions

- Whether the change view is `context --changed` enhanced, or a new
  `context --change <id>` selector.
- The `(req: …)` tagging syntax and whether it is enforced.
- How a multi-agent or multi-PR change reconciles a single task list.
