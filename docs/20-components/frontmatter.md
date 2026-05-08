---
id: frontmatter
title: Frontmatter
audience: explanation
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes:
  - src/irminsul/frontmatter.py
---

# Frontmatter

Every doc atom carries a YAML frontmatter block matching Appendix B of the [reference](../90-meta/doc-system.md). The schema validates required fields (`id`, `title`, `audience`, `tier`, `status`, `owner`, `last_reviewed`) and parses optional ones (`describes`, `depends_on`, `supersedes`, `superseded_by`, `tags`, `related_adrs`, `children`).

`extra="allow"` is intentional — projects extend the schema with their own fields. Strictness comes from validating canonical fields, not from forbidding unknown ones.

`parse_doc()` returns either a `ParsedDoc` (success) or a `ParseFailure` (YAML error or schema rejection). Callers decide how to surface failures — the [DocGraph](docgraph.md) collects them and the [frontmatter check](checks.md) translates them to findings.

`expected_id_for(path)` codifies the filename rule: `INDEX.md` files take their parent folder's name; everything else uses the filename stem.
