---
id: frontmatter
title: Frontmatter
audience: explanation
tier: 3
status: stable
describes:
  - src/irminsul/frontmatter.py
  - src/irminsul/frontmatter_edit.py
tests:
  - tests/test_frontmatter.py
  - tests/test_frontmatter_edit.py
---

# Frontmatter

Every doc atom carries a YAML frontmatter block matching Appendix B of the [Doc Atom reference](doc-atom.md). The canonical field surface is defined by `DocFrontmatter` in `src/irminsul/frontmatter.py`.

`extra="allow"` is intentional — projects extend the schema with their own fields. Strictness comes from validating canonical fields, not from forbidding unknown ones.

`parse_doc()` returns either a `ParsedDoc` (success) or a `ParseFailure` (YAML error or schema rejection). A failure also carries a machine-readable `data` decomposition of the first validation error (a kebab-case `problem` key plus the offending field/value), so downstream findings can expose structure instead of prose. Callers decide how to surface failures — the [DocGraph](docgraph.md) collects them and the [frontmatter check](checks.md) translates them to findings.

`expected_id_for(path)` codifies the filename rule: folder index docs take their parent folder's name; everything else uses the filename stem.

The RFC lifecycle fields live here too ([RFC 0029](../80-evolution/rfcs/0029-bound-change-loop.md)): `rfc_state` has four canonical values (`draft`, `accepted`, `implemented`, `rejected`) plus deprecated aliases (`open`, `fcp`, `withdrawn`) that `canonical_rfc_state()` resolves during the deprecation window; `RFC_STATE_TRANSITIONS` is the single table of legal next states. `resolved_by` is required for both `accepted` and `implemented`. `affects` declares the component ids a proposal intends to change (`[]` means intentionally none) and `direction` marks foundation impact as `extends` or `revises`.

The write side lives in `src/irminsul/frontmatter_edit.py`: round-trip helpers (`set_value`, `add_to_list`, `remove_inventory_item`) that the deterministic [fix](new-list-regen.md) actions share so every rewrite re-emits keys in canonical order, leaves the body untouched, and is idempotent.

## Scope & Limitations

Frontmatter parsing enforces structural field correctness only — it does not evaluate prose style or content quality. It does not validate `describes:` glob patterns (that is the `globs` check). Unknown fields are silently accepted (`extra="allow"`), not validated.
