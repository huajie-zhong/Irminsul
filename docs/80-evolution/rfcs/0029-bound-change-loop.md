---
id: 0029-bound-change-loop
title: "Bound changes: turn the RFC into a code-bound proposal-to-verification loop"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0029: Bound changes — the proposal-to-verification loop

## Summary

This is the umbrella RFC for a stack (0029–0034) that grows irminsul's existing
RFC/ADR machinery into a complete development *loop*: **propose → implement →
accept → verify → propose-from-truth**. The loop is the same shape spec-driven
tools offer (propose / apply / archive), with one structural
difference that is the whole point — every step is **bound to code** and stays
bound, so the next iteration always departs from a verified base instead of a
prose document that has silently rotted.

The governing law of the stack, and the reason it is not just a re-skin of an
existing tool, is **derive, don't declare** — the change-loop application of the
project's own *derive, don't materialize* principle
([`principles.md`](../../00-foundation/principles.md)). An RFC declares only what
code cannot produce; every binding fact (which code, which surface, which owning
component, which backlink) is *derived* from the diff and the
[`DocGraph`](../../20-components/docgraph.md), never copied into the RFC.

This RFC defines the shared model and lands **iteration 1**: the minimal closed
loop — an RFC that names the components it affects, and a check that fails when an
accepted RFC's affected code has no doc coverage. The later RFCs add requirements
(0030), tasks (0031), accept-time anchoring (0032), the derived layered-impact
view (0033), and the base-truth gate plus MCP loop surface (0034).

## Motivation

irminsul already detects rot *after the fact* (mtime-drift, staleness) and, with
[`0021-code-doc-cochange`](0021-code-doc-cochange.md), at the PR gate. What it does
not have is a *forward* artifact that records, at proposal time, the binding a
change is promising to honor — so that "did this change land correctly?" becomes a
deterministic check rather than a review judgment.

Spec-driven tools occupy exactly this forward slot, but their specs are born
unbound: a proposal is prose, merged into a canonical spec tree, and never
reconciled against the implementation again. Each new proposal then plans on a base
nobody verified. The faster the loop runs, the more iteration N+1 compounds
iteration N's drift. That missing beat — *confirm the base is still true before
stepping forward* — is precisely the gap irminsul's check engine already fills for
docs. This stack connects the forward artifact (the RFC) to that engine so the
two halves become one loop.

## Detailed Design

### The change artifact is the RFC (no new tree)

A "change" is not a new directory or schema; it is the existing RFC under
`docs/80-evolution/rfcs/`, with a small amount of non-derivable intent and a
lifecycle (`rfc_state`) that already exists
([`0017-rfc-resolution-check`](0017-rfc-resolution-check.md)). Nothing about the
9-layer structure changes. This keeps the loop inside irminsul's own model instead
of importing a parallel `changes/` + `specs/` split.

### The derive-don't-declare law

Every fact a change could record falls into the two buckets of
[`principles.md`](../../00-foundation/principles.md):

1. **Derivable** — which components the change touches, which globs, which
   surfaces it added, the backlinks. These are **never written into the RFC**.
   They are computed on demand from the diff and the graph (see below).
2. **Non-derivable** — the *intent* (why), the *requirements* (behavior promised,
   added in 0030), and the *direction* flag (does this revise a foundation
   principle? — a human judgment). Only these are authored.

The consequence is a deliberately tiny frontmatter. The naive "footprint" — globs,
surfaces, component lists — would duplicate the component doc's `describes:` and the
derived `irminsul surface` output, creating a second home for one fact (a Law 1
violation, [`laws.md`](../../00-foundation/laws.md)) and a committed cache that goes
stale. The law forbids it.

### What the human writes (iteration 1)

```yaml
# frontmatter additions — all optional, all non-derivable
intent: "Enterprise users need SSO login."
affects: [auth]          # owning component IDs this change targets (pointers, not globs)
direction: extends       # extends | revises (only when foundation is touched)
```

`affects` lists **component doc ids**, not paths or globs — a pointer to where the
binding facts already live, not a copy of them.

### What is derived (iteration 1 check)

A new soft-deterministic check, `change-binding`, runs against an accepted RFC
(`rfc_state: accepted`) that declares `affects`. Its primary signal is **binding
divergence**: the components the change *actually* touched, derived from the diff,
versus the components it *declared*. Touched components come from the same
`resolve_claims` ownership logic (`src/irminsul/checks/uniqueness.py`) that
[`coverage`](../../20-components/checks.md) and the `context --changed` co-change
fold ([`0021-code-doc-cochange`](0021-code-doc-cochange.md)) already use, so
"which components did this change really touch" is a derivation, never a second
declaration. The check flags either side of the gap:

- **Declared-but-untouched** — `affects: [auth]` while the diff changed no code
  `auth` owns: the pointer is aspirational, not bound.
- **Touched-but-undeclared** — the diff changed code owned by `billing`, but
  `billing` is absent from `affects`: an unbound side effect slipped in.

This divergence is the net-new guarantee, and it is genuinely new: no existing
check compares a change's *declared intent* against its *derived footprint*. The
coverage and ref checks already prove a component owns real source and that an
id resolves, so `change-binding` does **not** re-litigate those — it only adds the
declared-vs-derived comparison and a cheap shape guard on the new keys
(`affects` is a list of existing component ids; `direction` is `extends|revises`),
since the lean frontmatter is `extra="allow"` and would otherwise swallow a typo
(`affect:`) silently.

Severity is `warning`, promotable to error under `--strict`, consistent with the
rest of the soft-deterministic set.

### Relationship to spec-driven tools

A spec-driven tool's proposal is prose with no hook into code; its validator
checks the spec's *internal grammar* only. This stack matches the
propose/apply/archive ergonomics (0030–0032) but adds the binding such tools
structurally cannot: the proposal names code it must own, and the engine proves
it. The naming convention
above (`propose`, the loop verbs) is intentionally familiar; the difference is
enforcement, not vocabulary.

## Drawbacks

- **A new lifecycle expectation.** Authors who never set `affects` get today's
  behavior unchanged, but the loop's value only appears once changes opt in.
- **Soft-by-default.** Iteration 1 warns rather than blocks; the divergence signal
  is real value at warning severity (it names unbound side effects today), but the
  *enforced* binding arrives with accept-time anchoring (0032) and the base-truth
  gate (0034).
- **Component-granularity only.** Iteration 1 binds at the component level; finer
  requirement-level binding waits for 0030/0032.

## Alternatives

- **A parallel `changes/` + `specs/` tree** (the spec-driven-tool shape) — rejected: it
  duplicates the 9-layer model, splits intent from the doc graph, and reintroduces
  an unbound canonical spec that rots.
- **Declare globs/surfaces in the RFC** (the naive footprint) — rejected: violates
  derive-don't-materialize and Law 1; the facts already have a home.
- **Do nothing / keep RFCs as pure prose** — the status quo; leaves the forward
  step disconnected from the verification engine, which is the entire gap.

## Unresolved Questions

- Check name: `change-binding` vs. folding into an existing check.
- Whether `affects` should accept layer ids (e.g. a whole component group) or only
  leaf component ids.
- The exact divergence policy: whether touched-but-undeclared and
  declared-but-untouched carry the same severity, and whether either tightens to an
  error once 0032 lands.
- CLI ergonomics for authoring (`irminsul new rfc --affects …` vs. interactive),
  deferred to the per-iteration RFCs.
