---
id: 0022-universal-fix-coverage
title: Universal auto-fix coverage
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0022: Universal auto-fix coverage

## Summary

Expand `irminsul fix` from a single-check surface (`supersession`) into a
focused manifest of deterministic, **finding-driven** fix methods across the
soft check registry. Track the rollout as one RFC so the contract stays
consistent. The contract itself is mostly already implemented in
`apply_fixes`; the only new contract element is a `--confirm` gate for
irreversible edits.

## Motivation

`irminsul fix` is plumbed at `src/irminsul/fix.py` and proposed by RFC-0002,
but only the `supersession` check emits `Fix` objects today. Several later
RFCs treat `irminsul fix` as the canonical low-touch maintenance command:

- RFC-0017's atomicity rule expects `irminsul fix` to align a resolved RFC's
  `status` and resolution scaffolding.
- RFC-0018 expects a required-update doc's inverse `implements:` link to be
  computable without hand-maintaining both sides.
- RFC-0019 expects the first use of a glossary term to be linkable on demand.
- RFC-0020 expects a drifted `inventory:` item to be prunable without a manual
  frontmatter edit.

Without expanded fix coverage these RFCs silently regress to "the agent does
this by hand," defeating the low-touch goal. The fix expansion is its own
RFC because every individual fix shares a contract — atomicity, dry-run, the
profile selector, and the confirmation gate — and the contract should be
specified once.

## Detailed Design

### Shared contract

Every `Fix` object implements the same shape already established by
`supersession` and enforced by `apply_fixes`:

- **Atomic** write through a same-directory temporary file plus `os.replace`,
  never partial. *(Already implemented.)*
- **Idempotent**: running the fix twice yields the same file. *(Already
  implemented — fixes that are no-ops on already-correct files produce no
  write.)*
- Honors **`--dry-run`** by emitting the planned write set without touching the
  filesystem. *(Already implemented.)*
- Honors **`--profile hard|configured|advisory|all-available`** by harvesting
  fixes only from checks active under that profile. *(Already implemented in
  `cli.fix`.)*
- Honors **`--confirm`** for irreversible edits (see below). *(New.)*
- Honors **`--check <name>`** to harvest fixes from a single check for targeted
  runs. *(New; resolves a prior Unresolved Question.)*

Because the first four properties already hold, the implementation work is
adding `fixes()` methods to checks plus the two new flags — not re-specifying
the write machinery.

### Rollout manifest

In rough priority order for agent leverage. Each item names the check whose
findings drive it; a fix only ever remediates a finding the check actually
emits.

1. **Supersession metadata** (`supersession`). Already shipped; listed here so
   the manifest is one inventory.
2. **Required-update back-link** (`decision-updates`, RFC-0018). When the check
   emits a `missing-backlink` finding, add the driving RFC's id to the required
   update doc's `implements:` field. This is a purely *additive inverse
   pointer*, so it applies without `--confirm`.
3. **Inventory item pruning** (`inventory-drift`, RFC-0020). When the check
   flags a declared `inventory:` item that no longer exists in code, drop that
   item from the block. The block is *curated human intent*, not a mirror of the
   surface, so the fix only removes items the author already declared — it never
   adds the full extracted surface back in. Removing curated content is
   irreversible-in-spirit, so it requires `--confirm`.
4. **RFC-resolution metadata alignment** (`rfc-resolution`, RFC-0017). For an
   RFC *already* in a terminal `rfc_state` (`accepted`, `rejected`, or
   `withdrawn`), align the load-bearing scaffolding the check flags: set
   `status: stable` and insert the missing scaffolding section as a stub —
   `## Resolution` for accepted, `## Rejection Rationale` / `## Withdrawal
   Rationale` for rejected / withdrawn. Requires `--confirm`. The stub is a
   scaffold for the human to fill; the fix does **not** decide the outcome —
   see out-of-scope below.
5. **Glossary auto-link** (`glossary-discipline`, RFC-0019). When the check
   emits the unlinked-term finding, wrap the first occurrence of the term with
   the glossary anchor link on the exact line the finding reports. Because it
   edits prose rather than frontmatter, it requires `--confirm`.

### Explicitly out of scope

- **Anchor re-pinning** (RFC-0024's `claim-anchor`). Re-pinning an anchor is a
  deliberate human acknowledgement that the prose was re-read and is still true;
  doing it automatically would rubber-stamp the staleness the anchor exists to
  catch. It stays its own command (`irminsul anchors --re-pin`), never an
  `irminsul fix` action.

- **The act of accepting an RFC** (RFC-0017). Choosing to accept is a human
  decision; no finding drives it, so it does not fit the finding→fix model. Only
  the *post-decision* metadata alignment (item 4) is a fix. The decision itself
  stays a deliberate edit (or a future dedicated command), never a fix.

- **AGENTS.md auto-section regeneration** (RFC-0013). This is already a command:
  `irminsul regen agents-md` regenerates the generated section from the graph.
  Folding it into `irminsul fix` would duplicate the `regen` surface, so the
  manifest defers to `regen` here rather than re-implementing it.

- **Stale-flag bumping.** Auto-advancing a staleness flag (e.g. bumping a doc to
  a "review" state because it has aged) rubber-stamps the very staleness the flag
  exists to surface — the same objection that excludes anchor re-pinning. It is
  also not what `stale-reaper` checks: that check flags `status: deprecated` docs
  past `deprecated_threshold_days`, where the remedy (delete, mark removed, or
  rewrite-and-recommit) is a human judgement, not a mechanical edit. Rejected.

- **Frontmatter normalization / dead-glob suggestion.** No check emits a finding
  for non-canonical key order, unknown keys, or a near-miss `describes` glob
  today, so there is nothing for a fix to remediate. These are deferred until a
  check first *detects* the condition; adding a fix before the finding exists
  inverts the finding→fix contract.

### Confirmation modes

`irminsul fix` defaults to applying fixes (subject to `--dry-run`). Fixes that
modify or remove existing content, or rewrite load-bearing metadata, are tagged
`requires_confirm` and are **skipped** unless `--confirm` is passed; without it,
the command lists them as planned-but-held writes. Purely additive inverse
pointers (item 2) apply without `--confirm`. This is stricter than the original
`supersession` behavior, and is intentional: the new fixes touch load-bearing
metadata and prose.

## Relationship to Existing RFCs

- Generalizes RFC-0002, which introduced the fix framework on supersession.
- Provides the underlying mechanics expected by RFC-0017 (metadata alignment),
  RFC-0018 (required-update back-link), RFC-0019 (glossary auto-link), and
  RFC-0020 (inventory rewrite).
- Defers to RFC-0013's existing `regen` surface for AGENTS.md rather than
  duplicating it.

## Drawbacks

A larger fix surface means a larger blast radius if a fix has a bug. The shared
contract (atomic, idempotent, dry-run respected, confirm-gated for irreversible
edits) is mitigation, but projects should pin the Irminsul version they use in
CI rather than tracking floating versions while the fix surface expands.

Each fix is one PR. Tracking the rollout as one RFC risks slow progress if later
items in the manifest never land. The RFC notes progress with a `## Status` log.

## Alternatives

- One small RFC per fix. Rejected because the contract is shared; several small
  RFCs would duplicate the contract text.
- Skip the RFC and add fixes ad hoc. Rejected because the contract needs to be
  specified before checks start emitting fixes that violate it.
- A maximal manifest covering every check (the original draft of this RFC).
  Rejected: it included fixes with no driving finding (frontmatter
  normalization, dead-glob), a fix redundant with `regen` (AGENTS.md), and a
  fix that rubber-stamps staleness (stale-flag bumping). Trimming to
  finding-driven, non-judgement fixes keeps the blast radius honest.

## Status

- Manifest item 1 (supersession): shipped pre-RFC.
- Manifest items 2–5: proposed here; each lands as its own PR.

## Unresolved Questions

- Should a planned-write report include the unified diff, or only the file path
  and description? Deferred: the current path+description report ships; a diff
  mode can be added later if noise proves acceptable.
