---
id: 0034-binding-readiness-and-agent-lifecycle
title: "Binding readiness and the governed agent lifecycle surface"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0034: Binding readiness and the governed agent lifecycle surface

## Summary

Close the bound-change loop with two pieces:

1. **Binding readiness** - compose existing deterministic checks into lifecycle-
   aware pre-proposal and pre-finalization reports. The report proves mechanical
   freshness and exposes semantic-review clues; it does not claim that all behavior
   is true.
2. **Agent lifecycle access** - expose read-only change status, verification,
   impact, and readiness through the existing MCP server, while confirmed lifecycle
   writes remain CLI actions until MCP has an explicit authorization model.

The result gives agents the missing RFC workflow: discover accepted work, inspect
implementation evidence, identify semantic questions, verify mechanical readiness,
and invoke a confirmed CLI transition after the human decision.

## Motivation

Irminsul currently gives agents generic repository context and check results but no
RFC-specific next action. `new rfc` scaffolds a document, `list lifecycle` reports
decision-update debt, and `fix` repairs individual findings; none answers whether a
particular accepted RFC is ready to finalize or why it is not.

The original "base truth" framing is too strong. Coverage, anchors, and co-change
can prove that bindings are structurally present and fresh relative to known code
changes. They cannot prove that behavior still satisfies prose requirements.
Irminsul should make the mechanical guarantee strong and make the remaining
semantic work obvious to the agent.

## Detailed Design

### Two readiness points

Readiness is a mode of `irminsul change verify`, not a duplicate registry check.
It composes checks and evidence for two transitions.

**Before accepting a draft:**

- RFC lifecycle and frontmatter shape are valid;
- `affects` is explicit, including `[]`;
- requirements are valid or explicitly unnecessary;
- tasks reference valid requirements or affected components;
- an ADR exists or is created as part of the confirmed transition;
- repository-wide hard failures are reported;
- feasibility and impact clues are presented for semantic review.

**Before finalizing accepted work:**

- a usable implementation diff baseline exists;
- declared and observed component scope is reconciled;
- hard checks pass and relevant configured findings are resolved or acknowledged;
- required docs and decision backlinks are complete;
- every code-backed requirement has confirmed promotion bindings;
- existing anchors in the affected scope are fresh;
- implementation and test evidence, gaps, and semantic-review clues are presented.

The result uses `mechanically_ready_for: accepted|implemented|none`. It never emits
`semantically_correct: true`.

### Pre-proposal baseline

When an agent begins a new RFC through `new rfc`, `orient`, or MCP, Irminsul first
runs a repository binding-readiness summary:

- hard-profile errors are blockers because the base graph is structurally invalid;
- stale anchors, undocumented source, lifecycle debt, and co-change findings are
  clues with source paths;
- unrelated configured warnings do not prevent drafting a proposal by default;
- `--strict` may require a clean configured profile for projects that want a
  repository-wide gate.

This prevents silent drift from disappearing into the next plan without making an
unrelated warning an unconditional barrier to recording a new idea.

### Scoped finalization gate

Pre-finalization readiness is scoped to the RFC's declared and observed components,
their promoted claims, required updates, and relevant graph neighbors. Global hard
errors still block because the graph cannot be trusted; unrelated soft warnings are
reported separately as repository debt.

Co-change evidence requires Git context. Baseline resolution follows 0029:
explicit `--base-ref`, CI base SHA, or local staged/unstaged changes. If none is
available, co-change is `unknown`, not clean, and implementation finalization is not
mechanically ready.

### Shared report contract

CLI and MCP return one versioned JSON shape:

```json
{
  "change": "0035-sso-login",
  "state": "accepted",
  "mechanically_ready_for": "implemented",
  "blockers": [],
  "evidence": [],
  "semantic_review": [],
  "repository_debt": [],
  "next_actions": []
}
```

Each blocker, evidence item, and clue carries paths, lines or symbols when known,
the producing check or derivation, and a suggested next command. This is the bridge
between deterministic mechanics and agent semantic work.

### CLI lifecycle surface

The command group defined in 0029 owns lifecycle behavior:

- `change status <id>` - current state, accepted backlog position, compact evidence,
  and valid transitions;
- `change verify <id>` - full readiness report without mutation;
- `change impact <id>` - layered evidence and review routes;
- `change transition <id> accepted|rejected --confirm` - human-authorized decision;
- `change finalize <id> --confirm` - confirmed promotion and implemented transition.

`irminsul list lifecycle --queue` expands to include accepted-but-not-implemented
RFCs and their next mechanical action. The agent protocol gains an explicit work
order: inspect accepted work, run status, implement, run verify, resolve semantic
clues, then finalize after authorization.

### Read-only MCP surface

The current MCP server is deliberately read-only. This RFC preserves that boundary
and adds thin wrappers over the shared CLI report functions:

- `change_status`;
- `change_verify`;
- `change_impact`;
- `binding_readiness`.

The tools are added to `mcp-server.md`'s watched inventory so
[`0028`](0028-mcp-tool-surface-governance.md) detects surface drift. Their tool
descriptions tell agents which evidence to inspect and which confirmed CLI command
to run next.

Lifecycle mutation is not exposed over MCP in this RFC. A future write surface must
define authorization, confirmation, dry-run visibility, and partial-failure
recovery instead of assuming read governance is sufficient for writes.

### Advisory semantic checks

Projects may enable LLM advisory checks that consume the same report and inspect
requirements against code and tests. Their findings appear under
`semantic_review`; they never change `mechanically_ready_for`, never run in the hard
profile, and never transition an RFC automatically.

This follows the existing principle: mechanical checks create reliable clues that
let agents focus semantic judgment where it is needed.

## Drawbacks

- **Not a truth oracle.** Binding readiness is intentionally narrower than semantic
  correctness; documentation and command wording must preserve that distinction.
- **Accepted backlog migration.** Existing accepted RFCs will appear unfinished
  until migrated or finalized as implemented.
- **Git-dependent evidence.** Complete finalization requires a known change range.
- **No MCP writes.** MCP-only clients can inspect and plan but must invoke or ask a
  user to invoke the confirmed CLI mutation.
- **Report complexity.** A useful agent packet needs stable categories and source
  attribution without becoming a second finding framework.

## Alternatives

- **Call the result base truth.** Rejected because anchor and coverage checks prove
  binding freshness, not semantic behavior.
- **Add a new monolithic readiness check.** Rejected because lifecycle readiness is
  composition over existing checks plus change evidence, not a new invariant.
- **Block proposal creation on every configured warning.** Rejected because
  unrelated debt should be visible without preventing a draft roadmap item.
- **Expose transitions and finalization as MCP writes immediately.** Rejected until
  the read-only server has an explicit write authorization design.
- **Let an advisory LLM result satisfy a mechanical gate.** Rejected by the project's
  hard/advisory separation.

## Unresolved Questions

- Versioning and extension rules for the shared change-report JSON schema.
- Whether accepted backlog ordering is by explicit priority, target date, or only
  deterministic document order; priority metadata is outside this RFC unless a real
  workflow requires it.
- Which configured findings are scoped blockers versus acknowledged warnings at
  finalization.
- How an agent records semantic-review acknowledgement without turning Irminsul
  into an identity or approval service.
