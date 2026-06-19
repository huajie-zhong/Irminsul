---
id: 0027-self-governance-affordances
title: Self-governance affordances for derivable surfaces
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0027: Self-governance affordances for derivable surfaces

## Summary

Irminsul ships strong anti-drift primitives — [`liar`](../../20-components/checks.md),
`inventory:` blocks with [`inventory-drift`](0020-inventory-drift.md), anchored
prose claims, and on-demand `surface` derivation. But they are all **opt-in by
declaration**: nothing *reminds* an author that the thing they are writing mirrors
a derivable surface and should be governed. The author has to already know the
primitive exists and remember to reach for it. That is a *pull* model, and its
blind spot is exactly the moment new code or docs are authored.

This RFC proposes adding authoring-time **reminders** (a *push* to complement the
pull) so that an agent or human is told, at the point of editing, "this is a
derivable surface — govern it or derive it." Three mechanisms, smallest first:
a one-line heuristic in the agent protocol, a contextual hint from `context` /
`orient`, and — the meaty, riskier piece — extending `liar` to see hand-enumerated
surfaces that live in **code**, not just doc prose.

## Motivation

The motivating incident is concrete. `irminsul orient` (added recently) emits a
curated command vocabulary that was first written as a hardcoded Python literal
(`_COMMANDS` in `src/irminsul/orient.py`) — a hand-enumeration of the CLI surface.
Rename or delete a command and `orient` would advertise a dead one, and **nothing
caught it**: not the dogfood `check --profile=hard`, not the tests. The agent that
wrote it never reached for `inventory:` or `surface`, even though they are the
purpose-built tools for exactly this.

The deeper problem is that the one check designed to stop this — `liar`, whose
docstring (`src/irminsul/checks/liar.py`) even cites the "regen agents-md
incident" as its reason for existing — scans only doc **prose** (markdown bodies
of stable explanation/reference docs). A hand-enumerated surface that lives in a
**Python literal** is structurally invisible to it. So the author got zero signal.

This is not inattention; it is a gap in the model. Governance is opt-in, and the
checker that should have nudged the author is blind to code. The orient case was
solved with a point-solution test, but that does not generalize — the next author
who hand-enumerates a surface somewhere new will hit the same wall.

This RFC is a follow-up to [RFC 0020](0020-inventory-drift.md) ("derive, don't
materialize"), which created these primitives but scoped them to prose, and a
sibling in spirit to [RFC 0021](0021-code-doc-cochange.md)'s "proactive signal" —
though that RFC solves a *different* problem (code-doc co-change), not "this file
is itself a derivable surface."

## Detailed Design

Three mechanisms, ranked by return on investment.

### 1. An authoring heuristic in the agent protocol (cheapest)

Add a single line to the edit-verify loop in `docs/90-meta/agent-protocol.md`:
*"If your change introduces an enumeration, list, or description that restates
something derivable from code (commands, endpoints, exports, env vars), govern it
(`inventory:` / anchor) or derive it (`surface`) — do not hand-maintain it."*
Cheap and immediate, but passive: it only helps an agent that reads and internalizes
the protocol.

### 2. A derivable-surface hint from `context` / `orient` (highest ROI)

When `irminsul context <path>` is run on a file that *is* a derivable surface
(it matches one of the `surface` extractors — e.g. `src/irminsul/cli.py` for the
`cli` kind), include a hint in the output: *"this file is a `cli` surface;
anything that restates it should use an `inventory:` block, an anchored claim, or
`irminsul surface cli`."* Agents already run `context` in the loop (and `orient`
first), so the reminder fires at the right place and time, converting pull into
push without anyone needing to read docs. This is the recommended core of the RFC.

### 3. Extend `liar` to code literals (the gap-closer, the risk)

Generalize `liar` so it can flag a **code** literal that enumerates at least the
threshold number of identities of a known surface kind — i.e. a tuple/list of
strings that are all current `cli`/`http`/`exports`/`env-vars` identities — and
tell the author to govern or derive it. This would have caught the orient
`_COMMANDS` tuple directly. It is the riskiest piece: distinguishing a
surface-mirroring literal from an incidental collection of strings needs a
threshold plus an allowlist, and false positives erode trust. It likely warrants
its own check name rather than overloading `liar`.

## Drawbacks

- Mechanism 3 carries real false-positive risk; a noisy "this looks like a
  surface" warning is worse than none.
- Mechanism 2 adds output to `context`/`orient` that could become noise if it
  fires too eagerly; it needs a precise "is this file a surface" test.
- More surface area for irminsul to own, for a benefit that is hard to measure
  (prevented future drift).

## Alternatives

- **Keep governance opt-in** (status quo) and rely on review discipline. Cheap,
  but the orient incident shows review misses it.
- **Documentation only** — the heuristic (mechanism 1) without the tooling.
  Weakest; passive guidance is what already failed here.
- **Point solutions** — solve each case as it appears, the way the orient
  vocabulary was solved with a dedicated test. Works locally, does not
  generalize, and re-incurs the same blindness for the next author.

## Unresolved Questions

- How to detect a "surface-mirroring" code literal (mechanism 3) without false
  positives — threshold, allowlist, and which AST shapes to consider.
- Where the `context`/`orient` hint threshold sits, and whether it should fire on
  any surface-kind file or only those a doc already claims.
- Whether mechanism 3 extends `liar` or is a new check, given `liar`'s current
  prose-only scope and docstring contract.
