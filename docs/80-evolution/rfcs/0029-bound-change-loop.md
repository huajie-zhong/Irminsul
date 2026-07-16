---
id: 0029-bound-change-loop
title: "Bound changes: a code-bound RFC lifecycle"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: implemented
affects:
- change
- checks
- frontmatter
resolved_by: docs/50-decisions/0016-freeze-implemented-rfc-records.md
required_updates: []
frozen_hash: "sha256:5f873795cfe4c588f70774f002197e02a7ca0ed1a1e63bf6dd35fdf3002f02d8"
---

# RFC 0029: Bound changes - a code-bound RFC lifecycle

## Summary

Turn the existing RFC into the forward artifact for significant change: a
potential roadmap item that can be proposed, accepted for implementation,
verified against repository evidence, and finally recorded as implemented. The
loop is **draft -> accepted -> implemented**, with **rejected** as the alternate
terminal outcome.

The stack follows two linked rules:

1. **Derive what is mechanically knowable.** Changed files, owning components,
   surfaces, backlinks, check findings, and anchor hashes come from the diff and
   the [`DocGraph`](../../20-components/docgraph.md); they are not copied into the
   RFC.
2. **Expose evidence for semantic judgment.** Intent, behavioral requirements,
   whether an implementation satisfies them, and the correct requirement-to-code
   relationship are not mechanically derivable. Irminsul supplies structured
   evidence and review clues to an agent or human, but never turns that judgment
   into a hard deterministic claim.

This sharpens the existing Harness Principle and the rule that build correctness
must not depend on LLM judgment
([`principles.md`](../../00-foundation/principles.md)). Mechanical checks remain
the gate; semantic review remains advisory and explicit.

This RFC defines the shared lifecycle, command surface, and iteration 1 binding.
Later RFCs add requirements (0030), implementation tasks and evidence (0031),
implementation finalization (0032), derived impact and review clues (0033), and
binding readiness plus agent access (0034).

## Motivation

Irminsul can scaffold an RFC, validate its terminal metadata, list unfinished
decision updates, and apply generic fixes. It cannot currently answer the change
questions an agent needs:

- Which RFCs are accepted but not implemented?
- What mechanical evidence exists for this RFC's implementation?
- What still needs semantic review?
- Is this RFC mechanically ready to become `implemented`?
- Which lifecycle transition is valid, and what must change atomically with it?

The current lifecycle also ends at decision resolution. `draft`, `open`, and
`fcp` describe proposal-process ceremony, while `accepted` is treated as terminal;
there is no state for delivered work. For Irminsul's issue-like RFC model, the
important distinction is simpler: proposed, approved, delivered, or declined.

## Detailed Design

### The RFC is the change artifact

A change remains the RFC under `docs/80-evolution/rfcs/`; no parallel change or
specification tree is added. The RFC owns non-derivable intent, requirements, and
implementation tasks. Component docs remain the canonical home for live claims
after implementation.

### Four-state lifecycle

The canonical lifecycle becomes:

| State | Meaning | Allowed next states |
|---|---|---|
| `draft` | Potential roadmap item; may be incomplete or under discussion. | `accepted`, `rejected` |
| `accepted` | Human-approved for implementation; implementation may not have started. | `implemented`, `rejected` |
| `implemented` | Implementation was mechanically verified, semantically reviewed, and finalized. | none; later change uses supersession |
| `rejected` | The project will not implement this proposal; rationale is recorded. | none |

`open` and `fcp` collapse into `draft`; projects that need discussion stages can
use review workflow outside the canonical RFC state. `withdrawn` collapses into
`rejected`, with the rationale recording whether the author withdrew it or the
project declined it.

Acceptance is a human decision, not a conclusion Irminsul derives. Implementation
readiness is a report, not another authored state. Only successful finalization may
write `rfc_state: implemented`.

Migration is mechanical because this repository currently uses none of the states
being collapsed:

- `open` and `fcp` -> `draft`;
- `withdrawn` -> `rejected`;
- existing `accepted` RFCs remain accepted until `change verify` confirms whether
  they qualify for `implemented`; an opt-in fix may migrate those whose Resolution
  already names shipped code and tests.

For compatibility with repositories already using the old enum, the parser accepts
`open`, `fcp`, and `withdrawn` for one deprecation window and emits a fixable
lifecycle warning. Checks treat `open`/`fcp` as draft and `withdrawn` as rejected
during that window; the next breaking release removes the aliases from
`RfcStateEnum`.

The frontmatter schema requires `resolved_by` for both `accepted` and
`implemented`. `rfc-resolution`, `decision-updates`, the RFC template, and
`list lifecycle` migrate together so no command observes a half-updated lifecycle.

### Lifecycle commands

Add an `irminsul change` command group:

- `change status <id>` - read-only lifecycle, requirements, task evidence,
  findings, and valid-next-action report;
- `change verify <id> [--base-ref REF]` - read-only implementation evidence and
  semantic-review clues, with machine-readable output;
- `change transition <id> accepted|rejected --confirm` - validate and apply a
  human-authorized decision transition atomically;
- `change finalize <id> --confirm` - run verification, promote confirmed claims,
  and transition `accepted -> implemented` atomically;
- `change impact <id> [--base-ref REF]` - the derived layered view from 0033.

`irminsul new rfc` remains the creation command. `change transition` and
`change finalize` support `--dry-run` and reuse the confirmation and idempotency
contract of [`fix`](../../20-components/cli.md). An agent may run every read
command freely; it runs a write command only after the user has authorized the
decision represented by that transition.

### Mechanical evidence and semantic-review clues

Every change report separates three categories:

- **Mechanical blockers** - invalid lifecycle transition, malformed requirement,
  unresolved component id, hard-check error, missing required update, stale
  anchor, or missing diff baseline.
- **Evidence** - changed files and owners, tests and docs touched, task-to-
  requirement links, surface deltas, check findings, and anchor candidates.
- **Semantic-review clues** - questions an agent or human must answer, such as
  whether a scenario is actually implemented, whether an edge case is missing, or
  which changed symbol is the correct evidence for a requirement.

The deterministic result may say `mechanically_ready: true`; it must not say the
behavior is correct. Agent-facing JSON includes the evidence references behind
each clue so an agent can inspect the relevant code rather than rediscover scope.

### What the author declares

The RFC body already owns intent through Summary and Motivation, so no duplicate
`intent:` frontmatter field is added. Two small fields carry judgments code cannot
produce:

```yaml
affects: [auth]       # component ids this proposal intends to change
direction: extends   # extends | revises; required only for foundation impact
```

`affects` is optional while the RFC is `draft`. It is required and explicit for
`accepted` and `implemented` RFCs; `affects: []` means the proposal intentionally
changes no owned source. This prevents silent opt-out while keeping early ideas
cheap to write.

### Iteration 1: change binding

A soft-deterministic `change-binding` check validates field shape and, when a diff
baseline is available, compares declared intent with the derived footprint. The
footprint uses `resolve_claims` ownership, the same primitive used by coverage and
`context --changed`:

- **declared but untouched** - a planned component has no implementation evidence;
- **touched but undeclared** - the implementation has an unplanned component side
  effect;
- **unowned change** - changed source has no component claim, delegated to
  `coverage` as a blocker.

The first two are review clues by default, because a valid implementation may
legitimately differ from its initial plan. Under `change finalize`, every
touched-but-undeclared component must be reconciled by updating `affects` or
recording a reviewed exception. Irminsul does not silently rewrite the plan.

Diff selection is explicit and never guesses a clean result: use `--base-ref`, a
CI-provided base SHA, or the local staged/unstaged set. If none is available, the
report returns `baseline: unknown` and cannot be mechanically ready for
finalization.

## Drawbacks

- **Lifecycle migration.** Existing checks and templates must migrate from six
  decision-process states to four delivery states.
- **Accepted RFC backlog.** `accepted` becomes an active queue rather than a
  terminal record, so repositories must decide which historical accepted RFCs are
  actually implemented.
- **Semantic boundary.** Evidence packets make agent review better and cheaper,
  but they cannot make semantic conclusions deterministic.
- **Git context.** Change binding needs a diff baseline; multi-PR changes must pass
  an explicit base rather than receiving a false clean result.

## Alternatives

- **Keep decision and delivery as separate enums.** More expressive, but creates a
  state-product with combinations such as accepted-but-abandoned and
  rejected-but-implemented. Four issue-like states match the intended workflow.
- **Keep `open` and `fcp`.** Rejected because Irminsul does not implement the
  governance process those states imply and no repository RFC currently uses them.
- **Derive semantic completion.** Rejected: code ownership and changed files are
  evidence, not proof that behavior satisfies a requirement.
- **Store globs, surfaces, or changed files on the RFC.** Rejected as committed
  caches of facts already derivable from code and the graph.

## Unresolved Questions

- Whether an accepted RFC may transition to rejected after implementation work has
  started, or whether that needs a distinct `abandoned` rationale category.
- Configuration of the default diff baseline for long-running and multi-PR work.
- Exact JSON schema shared by CLI and MCP change reports.

## Resolution

Implemented before 2026-07-15 and recorded by
[`ADR-0016`](../../50-decisions/0016-freeze-implemented-rfc-records.md).
