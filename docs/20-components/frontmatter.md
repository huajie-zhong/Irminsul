---
id: frontmatter
title: Frontmatter
audience: explanation
tier: 3
status: stable
describes:
  - src/irminsul/frontmatter.py
tests:
  - tests/test_frontmatter.py
---

# Frontmatter

Every doc atom carries a YAML frontmatter block matching Appendix B of the [Doc Atom reference](doc-atom.md). The canonical field surface is generated from `DocFrontmatter` in the [frontmatter fields reference](../40-reference/frontmatter-fields.md).

`extra="allow"` is intentional — projects extend the schema with their own fields. Strictness comes from validating canonical fields, not from forbidding unknown ones.

`parse_doc()` returns either a `ParsedDoc` (success) or a `ParseFailure` (YAML error or schema rejection). Callers decide how to surface failures — the [DocGraph](docgraph.md) collects them and the [frontmatter check](checks.md) translates them to findings.

`expected_id_for(path)` codifies the filename rule: folder index docs take their parent folder's name; everything else uses the filename stem.
