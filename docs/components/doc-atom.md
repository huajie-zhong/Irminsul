---
id: doc-atom
title: The Doc Atom Specification
status: stable
describes: []
---

# The Doc Atom

A "doc atom" is the smallest unit of documentation that has a single purpose. Every doc in the system is an atom, defined by required frontmatter:

```yaml
---
id: composer
title: Composer Component
status: stable              # draft | stable | deprecated | removed
describes:                  # source files this doc claims to describe
  - app/composer/*.py
tests:                      # required in layers with require_tests
  - tests/test_composer.py
depends_on:                 # ids of other docs this one relies on
  - planner
supersedes: []              # ids of older docs this replaces
---
```

This frontmatter is the contract; the full field set is described with the [frontmatter parser](frontmatter.md), and the rules a doc follows come from its [layer](../architecture/layers.md). Checks read it to enforce single ownership of source files (`uniqueness`), require tests in layers that ask for them (`coverage`), and flag docs whose described source changed more recently (`mtime-drift`), while `irminsul refs` derives backlinks from `depends_on`.

## Scope & Limitations

This doc describes the frontmatter contract only; validation lives with the [frontmatter parser](frontmatter.md), and the rules a layer adds are configured under `[layers]`.
