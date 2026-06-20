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

`parse_doc()` returns either a `ParsedDoc` (success) or a `ParseFailure` (YAML error or schema rejection). Callers decide how to surface failures — the [DocGraph](docgraph.md) collects them and the [frontmatter check](checks.md) translates them to findings.

`expected_id_for(path)` codifies the filename rule: folder index docs take their parent folder's name; everything else uses the filename stem.

The write side lives in `src/irminsul/frontmatter_edit.py`: round-trip helpers (`set_value`, `add_to_list`, `remove_inventory_item`) that the deterministic [fix](new-list-regen.md) actions share so every rewrite re-emits keys in canonical order, leaves the body untouched, and is idempotent.

## Scope & Limitations

Frontmatter parsing enforces structural field correctness only — it does not evaluate prose style or content quality. It does not validate `describes:` glob patterns (that is the `globs` check). Unknown fields are silently accepted (`extra="allow"`), not validated.
