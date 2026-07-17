---
id: frontmatter
title: Frontmatter
audience: explanation
tier: 3
status: stable
describes:
  - src/irminsul/frontmatter.py
  - src/irminsul/frontmatter_edit.py
  - src/irminsul/rfc_freeze.py
tests:
  - tests/test_frontmatter.py
  - tests/test_frontmatter_edit.py
  - tests/test_rfc_freeze.py
implements:
  - 0035-rfc-lifecycle-integrity-and-frozen-records
---

# Frontmatter

Every doc atom carries a YAML frontmatter block matching Appendix B of the [Doc Atom reference](doc-atom.md). The canonical field surface is defined by `DocFrontmatter` in `src/irminsul/frontmatter.py`.

`extra="allow"` is intentional — projects extend the schema with their own fields. Strictness comes from validating canonical fields, not from forbidding unknown ones.

`parse_doc()` returns either a `ParsedDoc` (success) or a `ParseFailure` (YAML error or schema rejection). A failure also carries a machine-readable `data` decomposition of the first validation error (a kebab-case `problem` key plus the offending field/value), so downstream findings can expose structure instead of prose. Callers decide how to surface failures — the [DocGraph](docgraph.md) collects them and the [frontmatter check](checks.md) translates them to findings.

`expected_id_for(path)` codifies the filename rule: folder index docs take their parent folder's name; everything else uses the filename stem.

The RFC lifecycle fields live here too ([RFC 0029](../80-evolution/rfcs/0029-bound-change-loop.md)): `rfc_state` has four canonical values (`draft`, `accepted`, `implemented`, `rejected`) plus deprecated aliases (`open`, `fcp`, `withdrawn`) that `canonical_rfc_state()` resolves during the deprecation window; `RFC_STATE_TRANSITIONS` is the single table of legal next states. `resolved_by` is required for both `accepted` and `implemented`. `affects` declares the component ids a proposal intends to change (`[]` means intentionally none) and `direction` marks foundation impact as `extends` or `revises`.

Stable ADRs can own retirement tombstones through `retires`
([RFC 0040](../80-evolution/rfcs/0040-retired-reference-audit.md)). Each entry has a
stable kebab-case `id`, `kind: cli-command|concept`, one or more exact `matches`,
and actionable `guidance`. CLI entries also require `surface_identity`, using
the identity returned by `irminsul surface cli` without the executable name:

```yaml
retires:
  - id: old-publish-command
    kind: cli-command
    surface_identity: publish
    matches:
      - acme publish
    guidance: Use the governed release workflow instead.
```

The schema validates the record shape and uniqueness within a doc. The
`retired-references` check decides whether the owner is an authoritative stable
ADR, detects a CLI identity that has become live again, and audits current
guidance. A current historical mention is explicit only when the exact phrase is
linked to the owning ADR.

The write side lives in `src/irminsul/frontmatter_edit.py`: round-trip helpers (`set_value`, `add_to_list`, `remove_inventory_item`) that the deterministic [fix](new-list-regen.md) actions share so every rewrite re-emits keys in canonical order, leaves the body untouched, and is idempotent.

## Frozen RFC records

An implemented RFC may carry `frozen_hash`, a full lowercase `sha256:` digest
([RFC 0035](../80-evolution/rfcs/0035-rfc-lifecycle-integrity-and-frozen-records.md)).
The seal covers the complete LF-normalized Markdown file except its own scalar
line. `rfc-lifecycle-integrity` verifies it; `seal_text()` is the deterministic
writer used by finalization and the migration fix.

## Scope & Limitations

Frontmatter parsing enforces structural field correctness only — it does not evaluate prose style or content quality. It does not validate `describes:` glob patterns (that is the `globs` check). Unknown fields are silently accepted (`extra="allow"`), not validated.
