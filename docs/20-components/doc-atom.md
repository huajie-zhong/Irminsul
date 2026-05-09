---
id: doc-atom
title: The Doc Atom Specification
audience: reference
tier: 2
status: stable
describes: []
---

# The Doc Atom

A "doc atom" is the smallest unit of documentation that has a single purpose. Every doc in the system is an atom, defined by required frontmatter:

```yaml
---
id: composer
title: Composer Component
audience: explanation       # tutorial | howto | reference | explanation
tier: 2                     # see tier system below
status: stable              # draft | stable | deprecated
describes:                  # source files this doc claims to describe
  - app/composer/*.py
  - app/prompts/composer/*
depends_on:                 # other docs this one references
  - reference/program-schema
  - reference/data-model
supersedes: []              # older docs this replaces
---
```

This frontmatter is the contract. CI reads it to enforce ownership, detect drift (`describes` files newer than the doc), generate backlinks (from `depends_on`), inject status banners, and route review reminders.
