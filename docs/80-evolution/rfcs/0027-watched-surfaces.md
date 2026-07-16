---
id: 0027-watched-surfaces
title: "Watched surfaces: pin a derivable surface and flag any change for review"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: implemented
affects:
- anchors
- checks
- frontmatter
- orient
- surface
resolved_by: docs/50-decisions/0016-freeze-implemented-rfc-records.md
required_updates: []
frozen_hash: "sha256:b4879a2f44d7a66dcd3bd1e8071ccb2f4a214fae5f91078cb3014db9c92d2672"
---

# RFC 0027: Watched surfaces

## Summary

Generalize irminsul's [anchored-claim](0024-anchored-prose-claims.md) idea — *pin a
piece of code, flag when it changes, re-read and re-pin* — from a **single symbol**
to an **entire derivable surface**. A doc opts a surface in; irminsul then flags
not only items that **disappeared** (which [`inventory-drift`](0020-inventory-drift.md)
already does) but also items that are **new** (completeness) and items whose
underlying code **changed** (freshness), prompting a human to look and re-pin.
Surface-agnostic (`cli`, `http`, `exports`, `env-vars`, generic) and opt-in.

The motivating consumer is `irminsul orient`'s command vocabulary, which today is
governed by a **hand-rolled test that reaches into an internal extractor**
(PR #45). That test exists only because no feature does this. This RFC turns it
into a feature; PR #47 (the planned follow-up) implements it and migrates orient
onto it, deleting the test (see *Migration*).

## Motivation

irminsul governs a derived surface in exactly **one** direction today: `inventory-drift`
checks that each declared item still exists in code (the anti-lie direction). By
deliberate design (RFC 0020, "derive, don't materialize") it refuses **completeness**
— it will never tell you a *new* command exists but is undocumented — and it has no
notion of **freshness** — a command whose behavior changed while its name stayed.

Separately, the `anchor` mechanism (RFC 0024) *does* implement "pin the current
state, flag any change, I'll re-read and re-pin" — but only for a **single** code
symbol tied to a paragraph of prose. It cannot watch a *set*, and it never notices
something *new*.

So the two halves a project actually needs — "tell me about anything new, gone, or
changed in this surface" — exist as separate, partial mechanisms. The result:

- **`orient`** had to hand-roll a test importing `CliTyperExtractor` to get the
  completeness direction. (PR #45.)
- **Any other project** — a CLI tool wanting "every command is documented and
  current," an API wanting the same for endpoints — hits the identical wall and
  hand-rolls the identical test. There is no opt-in feature to turn on.

This is a general capability gap, not an orient quirk, and it is not CLI-specific.

## Detailed Design

### The model

A *watched surface* is an `inventory:` entry that pins a snapshot of a derivable
surface and asks irminsul to flag any diff against the live surface. It extends the
existing entry (`kind`, `source`, `items`) with opt-in fields, so the RFC 0020
default — accuracy only, no completeness pressure — is unchanged for entries that
don't opt in:

```yaml
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items: [orient, context, refs, surface, check, fix, list undocumented]
    complete: true                    # NEW: flag live identities not in items/omit
    omit: [init, seed, anchors]       # NEW: identities deliberately excluded
    fingerprints:                     # NEW (optional): pin each item's code shape
      check: a1b2c3
      surface: d4e5f6
```

### What the check emits (per watched entry)

Against the live surface derived from `source` (via the existing `get_extractor`),
at full-identity granularity:

- **removed / renamed** — an `items` identity not in the live surface → warn
  (today's `inventory-drift` behavior; a rename is a removed-plus-new pair).
- **new / uncovered** — a live identity in neither `items` nor `omit`, when
  `complete: true` → warn ("document it or add it to `omit`"). This is the
  completeness direction `inventory-drift` refuses by default.
- **rotted omit** — an `omit` identity no longer in the live surface → warn.
- **changed** — when `fingerprints` is present, an item whose pinned fingerprint no
  longer matches its current code shape → warn ("re-read its docs and re-pin").
  Reuse the normalization/hashing already in `irminsul.anchors` (the `resolve`
  path behind `claim-anchor`); an unpinned item is an info nudge, mirroring anchor.

Severity is `warning` (consistent with `inventory-drift` and `claim-anchor`),
promotable to error under `--strict`.

### Re-pin workflow

Mirror the existing anchor lifecycle: `irminsul anchors --re-pin` (or a
`surface --re-pin`) regenerates `items`/`fingerprints` from the live surface and
writes them back to frontmatter, so resolving a flagged change is one command plus
a human review. This is the "I will take a look" step made concrete.

### Implementation staging (for PR #47)

- **Phase 1 — completeness** (`complete:` + `omit:`): no hashes, pure set diff over
  the extractor output. Small, and it is exactly what `orient` needs; orient
  migrates here and its hand-rolled test is deleted.
- **Phase 2 — freshness** (`fingerprints:` + re-pin): reuses `irminsul.anchors`
  hashing. Heavier; can land in the same PR or a follow-on.

### orient as the first consumer (dogfood)

orient.md's existing `inventory:` block gains `complete: true` and an `omit:` list
(the contents of `_OMITTED`); the bespoke validation in `orient.py` and its test
are removed in favor of the general check (see *Migration*). orient keeps emitting
its curated `_COMMANDS` — that is the report payload, not governance logic.

## Migration — what PR #45 leaves stale for PR #47 to remove

PR #45 is the **interim** fix: it makes orient's vocabulary correct today, but with
bespoke, orient-only machinery. Once the watched-surface check exists, PR #47
should reach the ideal state by **removing**:

- **`tests/test_orient_vocabulary.py`** — the entire hand-rolled gate; the general
  check (run in `irminsul check`) replaces it.
- **`evaluate_vocabulary()` and `command_path()` in `src/irminsul/orient.py`** — the
  bespoke accuracy+coverage logic; subsumed by the check.
- **`_OMITTED` in `src/irminsul/orient.py`** — moves into orient.md's inventory
  `omit:` list (data, not code).
- **The `tests:` reference** to `test_orient_vocabulary.py` in `docs/20-components/orient.md`.
- **The Scope & Limitations prose** in orient.md describing the test — rewritten to
  point at the watched-surface check.

PR #47 then **adds** to orient.md's inventory block: `complete: true` + the `omit:`
list. What **stays**: `_COMMANDS` (the emitted vocabulary) and the `inventory:`
block itself (now a watched surface). Net: orient is governed by a real, general,
opt-in irminsul feature with zero orient-specific governance code.

## Drawbacks

- **Freshness re-pin churn.** `fingerprints` fire on *any* code change to a watched
  item, even cosmetic ones — the same noise as `anchor`. Accepted by design: the
  whole model is "flag it, a human reviews," and Phase 1 (completeness) carries
  none of this churn.
- **Frontmatter weight.** Pinned snapshots (especially fingerprints) make
  frontmatter verbose for large surfaces; a sidecar store is an open question.
- **Opt-in burden.** Completeness must be turned on per surface to honor RFC 0020's
  default; projects that want it must say so.

## Alternatives

- **Status quo / per-project hand-rolled tests** (what orient does in PR #45) —
  works locally, governs only that project, reaches into internals; does not
  generalize.
- **A separate parallel check** instead of extending `inventory:` — splits one
  coherent concept ("watch this surface") across two mechanisms.
- **Reminder affordances only** — an earlier framing of this RFC proposed nudging
  authors (a protocol heuristic, a `context`/`orient` hint, extending `liar` to
  code literals) instead of providing the governance feature. Useful as a
  complement, but it leaves every project still hand-rolling the actual check; the
  watched-surface feature is the substantive fix.

## Unresolved Questions

- Extend `inventory-drift` in place, or add a distinct `surface-watch` check name?
- Where fingerprints live for large surfaces — frontmatter vs. a sidecar snapshot.
- Diff granularity for `complete:` — full identity (orient wants `list undocumented`
  precision) vs. top-level groups.
- The re-pin command surface (`anchors --re-pin` vs. a new `surface --re-pin`).
- Whether Phase 2 (freshness) should ship with PR #47 or as a follow-on.

## Resolution

Implemented before 2026-07-15 and recorded by
[`ADR-0016`](../../50-decisions/0016-freeze-implemented-rfc-records.md). Watched
surface completeness, omissions, fingerprints, and re-pinning are live behavior.
