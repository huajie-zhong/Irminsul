---
id: a-snapshot-is-judged-by-its-own-configuration
title: "A snapshot is judged by its own configuration"
status: stable
describes: []
summary: Ownership at the merge base is read with the merge base's `irminsul.toml`, so one change cannot alter what the base meant; the governing claim `adoption-exception-does-not-return` says so.
---

# A snapshot is judged by its own configuration

## Status

Accepted.

## Context

Ownership is not a declaration on its own. It is a declaration plus the rule that accepts
it, and half of that rule lives in `irminsul.toml`: `governed_as_test` gives a file in a
declared test root to the test policy *only where no source root also covers it*, so
`paths.source_roots` decides whether an `owns_tests:` entry is ownership at all.

`diff-integrity` asks one question about the merge base — did this recorded file have an
owner there — and answers it by reading the base's documents out of git. It read them
through the head's configuration, which made the answer a function of the change being
judged. One commit could delete an owning document and add that document's test root to
`source_roots`: adding a root is a widening, no rule reports it, and the base's surviving
declaration stopped counting as ownership. The file was then unowned at the head with its
path still in the adoption record, and the exception the deleted owner had retired came
back with nothing saying so.

The [adoption record](../components/adoption-record.md) exists because the merge base is
the only thing that can supply the state a stale record failed to record. That only holds
while the base is asked about on its own terms.

## Decision

Every question about a snapshot is answered with that snapshot's own configuration and its
own adoption record.

- `_owned_at_ref` takes the configuration of the ref it reads, which is the one
  `diff-integrity` already parses at the merge base and already reports as a warning when
  it will not load.
- The seal resolves two `SourceMap`s, one per side, each from that side's configuration and
  record, and compares them.
- The governing claim `adoption-exception-does-not-return` states the rule, so a later
  change that reverts to the head's configuration has to come back through this file.

The working tree is the one input that is shared, and it is not a snapshot: there is a
single checkout, and a sibling repository is cloned into it once. So a declared root's
membership is walked in the tree that exists, on both sides.

## Alternatives Considered

**Ask with the head's configuration and accept the gap.** Rejected: it makes the base's
meaning editable by the change under review, which is the one thing a merge base is for.

**Report any configuration change as a weakening.** Rejected as both too loud and too
quiet — widening `source_roots` is the ordinary way to bring a tree under governance, and a
rule that fired on every widening would be turned off long before the day it mattered.

**Seal `paths.test_roots` against narrowing, like the thresholds.** Rejected as aiming at
the symptom: the same asymmetry would return through any other configuration-dependent
rule. It remains available if a narrowing turns out to need reporting for its own sake.

## Consequences

Nothing stops being reported; one thing starts. A change that widens `source_roots` while
deleting an owner is now `diff-integrity/adoption-exception-revived`, where before it was
silent — so a repository doing that deliberately has to document the file or say so in a
decision record.

The base's configuration has to be readable for the base to be judged on its own terms.
When it is not, `diff-integrity/base-config-unreadable` reports the fallback to the head's
configuration as a warning, and the judgement is worth what that warning says it is. That
limit is inherited, not introduced here.
