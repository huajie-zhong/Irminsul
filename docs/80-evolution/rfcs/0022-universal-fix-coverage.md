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
manifest of deterministic fix methods across the soft check registry. Track
the rollout as one RFC so the contract stays consistent.

## Motivation

`irminsul fix` is plumbed at `src/irminsul/fix.py` and proposed by RFC-0002,
but only the `supersession` check emits `Fix` objects today. Several later
RFCs treat `irminsul fix` as the canonical low-touch maintenance command:

- RFC-0016 step 7 invokes `irminsul fix` to update an old doc's metadata when
  a new doc supersedes it.
- RFC-0017's atomicity rule expects `irminsul fix` to set `rfc_state`,
  `status`, and `resolved_by` together.
- RFC-0013 expects `irminsul fix` to regenerate `AGENTS.md`'s auto section.
- RFC-0019 and RFC-0020 both propose fix actions that need a shared
  implementation surface.

Without expanded fix coverage these RFCs silently regress to "the agent does
this by hand," defeating the low-touch goal. The fix expansion is its own
RFC because every individual fix shares a contract — atomicity, dry-run, the
profile selector — and the contract should be specified once.

## Detailed Design

### Shared contract

Every `Fix` object implements the same shape already established by
`supersession`:

- Atomic write through a temporary file plus rename, never partial.
- Idempotent: running the fix twice yields the same file.
- Honors `--dry-run` by emitting the planned write set without touching the
  filesystem.
- Honors `--profile hard|configured|advisory|all-available` by harvesting
  fixes only from checks active under that profile.

### Rollout manifest

In rough priority order for agent leverage:

1. **Frontmatter normalization** (`FrontmatterCheck`). Canonical key order,
   normalized casing, unknown keys moved to a `legacy:` block rather than
   dropped.
2. **Supersession metadata**. Already shipped; listed here so the manifest is
   one inventory.
3. **AGENTS.md auto-section** (RFC-0013). Regenerate the generated portion of
   `docs/AGENTS.md` while preserving the curated foundations section and the
   protocol-summary section.
4. **Glossary auto-link** (RFC-0019). Wrap the first occurrence of a known
   `match` term with the glossary anchor link.
5. **Inventory rewrite** (RFC-0020). Replace the `inventory:` block in a
   component doc with the extractor's output.
6. **Dead-glob suggestion**. When a `describes` glob matches zero files,
   propose the nearest existing path via Levenshtein distance and write the
   replacement on confirm.
7. **Stale-flag bumping** (`stale-reaper`). `status: stable` past
   `stale_after_days` becomes `status: review` with a timestamp.
8. **RFC state transition** (RFC-0017). On accepting an RFC, atomically set
   `rfc_state: accepted`, `status: stable`, `resolved_by`, and insert a stub
   `## Resolution` section.
9. **Follow-up back-link** (RFC-0018). When a follow-up doc is created, add
   its `implements:` field via fix so the inverse relationship is computable
   without manual maintenance on both sides.

### Confirmation modes

For irreversible edits (RFC state transitions, dead-glob replacements,
inventory rewrites), `irminsul fix` requires `--confirm` to write. Without
it, the command prints planned writes. This is stricter than the current
behavior for `supersession`, and is intentional: the new fixes touch
load-bearing metadata.

## Relationship to Existing RFCs

- Generalizes RFC-0002, which introduced the fix framework on supersession.
- Provides the underlying mechanics expected by RFC-0013 (AGENTS.md regen),
  RFC-0017 (atomic state transition), RFC-0018 (follow-up back-link),
  RFC-0019 (glossary auto-link), and RFC-0020 (inventory rewrite).

## Drawbacks

A larger fix surface means a larger blast radius if a fix has a bug. The
shared contract (atomic, idempotent, dry-run respected) is mitigation, but
projects should pin the Irminsul version they use in CI rather than tracking
floating versions while the fix surface expands.

Each fix is one PR. Tracking the rollout as one RFC risks slow progress if
later items in the manifest never land. The RFC will note progress with a
`## Status` log similar to RFC-0008's rollout style.

## Alternatives

- One small RFC per fix. Rejected because the contract is shared; nine small
  RFCs would duplicate the contract text.
- Skip the RFC and add fixes ad hoc. Rejected because the contract needs to
  be specified before checks start emitting fixes that violate it.

## Unresolved Questions

- Should a planned-write report include the unified diff, or only the file
  path? The diff is more useful but increases noise on large changes.
- Should `irminsul fix` accept a per-check subset (e.g., `irminsul fix
  --check inventory-drift`) for targeted runs?
