---
id: 0019-glossary-discipline
title: Glossary discipline and terminology resolution
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0019: Glossary discipline and terminology resolution

## Summary

Add a soft deterministic check named `glossary-discipline` and a small metadata
shape on `GLOSSARY.md` entries so that terms used in docs stay defined, defined
terms stay used, and canonical names win over drifting synonyms.

## Motivation

The project ships a glossary, but nothing enforces that it stays connected to
the doc body. Terms can be used without being defined, glossary entries can rot
unused, and synonyms ("doc system" vs "doc graph") drift apart with no signal.
None of RFC-0013 through RFC-0018 covers this.

Agents asked to write or revise docs are the most likely source of synonym
drift, because they will invent plausible-sounding paraphrases unless an
explicit canonical form is enforced. A check is the smallest fix.

## Detailed Design

### Glossary entry metadata

Each `GLOSSARY.md` entry gains a small metadata block under its heading, before
the prose definition:

```markdown
## DocGraph

match: ["DocGraph", "doc graph"]
forbidden_synonyms: ["doc system"]
case_sensitive: true

The single in-memory data structure built per CLI invocation. ...
```

- `match`: strings that count as a use of this term in doc bodies.
- `forbidden_synonyms`: strings that must never appear; the check suggests the
  canonical name when it finds one.
- `case_sensitive`: defaults to `true` for technical names; set `false` for
  natural-language terms.

Bare entries with no metadata block remain valid; the check only enforces what
the entry declares.

### Check rules

Add `glossary-discipline` to the soft deterministic registry with three
sub-rules:

1. *Defined → used.* A glossary entry whose `match` strings appear nowhere in
   doc bodies, and which has zero inbound weak references, emits a soft
   finding. Uses the existing weak-link index in
   `src/irminsul/docgraph_index.py`.
2. *Canonical only.* A doc body containing any `forbidden_synonyms` string
   emits an error with a suggestion pointing at the canonical heading. Promotes
   to a hard finding under `--strict`.
3. *Used → defined (advisory).* A doc body using a known `match` string without
   linking to the glossary anchor emits an info-level finding suggesting an
   auto-link. False-positive-prone, kept advisory by default.

### Why opt-in matching

Scanning every English word against an "is this term defined?" rule is
hopeless. The glossary declares what to look for; everything else is silence.
This keeps the check deterministic and tractable on large doc trees.

### Auto-fix

Rule 3 emits a `Fix` that wraps the first occurrence of a `match` string with
the glossary anchor. The implementation lands inside the rollout proposed by
RFC-0022.

## Relationship to Existing RFCs

- Reuses the weak-link index built by `DocGraph` (consumed today only by
  `OrphansCheck`); the same index powers RFC-0014.
- Auto-fix support is part of RFC-0022.
- Does not depend on RFC-0017 or RFC-0018.

## Drawbacks

The metadata block under each glossary heading adds a small authoring burden.
Entries without the block still work; only entries that declare metadata are
checked.

Rule 3 will produce noise if authors quote a term in passing without intending
a glossary reference. Keeping it info-level mitigates this; strict mode is
opt-in.

## Alternatives

- Embed term metadata in YAML frontmatter at the top of `GLOSSARY.md` rather
  than per-entry. Rejected because the per-entry block keeps each term and its
  rules co-located.
- Use a separate `glossary.yaml`. Rejected because the markdown definition and
  the metadata should not drift across files.
- Build a stemmer that catches every English variant. Rejected because false
  positives dominate, and the canonical-only rule already covers the high-value
  case.

## Unresolved Questions

- Should plural forms be handled by a small stemmer or by explicit `match`
  enumeration? The first version should prefer explicit enumeration.
- Should rule 3 be opt-in per doc via frontmatter rather than globally?
