---
id: frontmatter
title: Frontmatter
status: stable
describes:
  - src/irminsul/frontmatter.py
  - src/irminsul/frontmatter_edit.py
  - src/irminsul/declared_tests.py
owns_tests:
  - tests/test_declared_tests.py
  - tests/test_frontmatter.py
  - tests/test_frontmatter_edit.py


inventory:
  - kind: frontmatter-fields
    source: src/irminsul/frontmatter.py
    explained_in: any
    omit:
      - body
      - body_offset
      - data
      - error
      - frontmatter
      - parts
      - raw
---

# Frontmatter

Every doc atom carries a YAML frontmatter block; the [Doc Atom reference](doc-atom.md) introduces its required fields. The canonical field surface is defined by `DocFrontmatter` in `src/irminsul/frontmatter.py`.

`extra="allow"` is intentional — projects extend the schema with their own fields. Strictness comes from validating canonical fields, not from forbidding unknown ones. The exception is a key that reads as a misspelled canonical field the doc does not set, such as `desribes` for `describes`: the field it meant to set stays empty, so every check that reads it goes quiet, and the `frontmatter` check reports the key as an error. A project's own key needs a name that cannot be mistaken for a field.

`parse_doc()` returns either a `ParsedDoc` (success) or a `ParseFailure` (YAML error or schema rejection). A failure also carries a machine-readable `data` decomposition of the first validation error (a kebab-case `problem` key plus the offending field/value), so downstream findings can expose structure instead of prose. Callers decide how to surface failures — the [DocGraph](docgraph.md) collects them and the [frontmatter check](checks.md) translates them to findings.

A `ParsedDoc` carries `body_offset` alongside `body`: the 1-based file line on which the body's first line sits. The parser strips the frontmatter block *and* the surrounding blank lines, so the offset cannot be recovered later from the frontmatter's length alone — it is measured against the original text while both are in hand, and [`DocNode.file_line()`](docgraph.md) is what checks report through.

Two optional fields feed single checks: `requires_env` lists the environment variables a component's source reads, verified by `requires-env`, and `target_decision_date` (`YYYY-MM-DD`) on an in-flight RFC makes `rfc-follow-through` warn once the date has passed.

Three fields name test paths and mean different things. `recommended_tests:` is what an
agent editing this component should run — a recommendation, not an inventory of what
covers the component and not evidence that anything ran; several docs may recommend one
shared integration test. `owns_tests:` is maintenance ownership of a test implementation
file, singular per file and written as exact paths, enforced by `test-ownership`. Left
unset, the recommendations default to the tests the doc owns, so an ordinary component
declares one list rather than two identical ones. `tests:` is the older spelling of
`recommended_tests:` and is still read; a doc that sets both is rejected rather than
merged, because they would be two sources of truth for one answer.

An `inventory:` entry names a surface `kind` and optional `source` glob, lists the `items` the doc calls out, and may opt into watching: `complete` compares the live surface against `items` plus `omit`, `fingerprints` pins each item's code shape, and `explained_in` (`self` or `any`) requires every live identity outside `omit` to be named in a code span of this doc or of any stable live doc. For a `cli-options` entry, a flag-shaped code span naming no live option is reported unless listed in `foreign` — but only in a span this project's inventory is entitled to judge: one that opens by invoking another program names that program's options, not ours.

A `claims:` entry pairs an assertion with the `evidence` it rests on, and declares a
`relation` saying what happens when the two disagree
([authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)).
`follows-evidence` is a report: the evidence wins, correcting the claim is routine, and it
is reserved for reports expensive to derive — cheap mechanical state belongs in
`inventory:` or nowhere. `governs-evidence` is a contract: the claim wins, so a violating
implementation is suspect, and rewording it is a change of intent rather than maintenance.
`review-on-divergence` is a semantic model, where neither side wins and a reader decides;
it is also what an omitted `relation` means, because nothing should infer an authority
nobody declared. A `planned` claim cannot be `follows-evidence` — a report cannot describe
behaviour that does not exist yet — and the schema rejects the pair.

`expected_id_for(path)` codifies the filename rule: folder index docs take their parent folder's name; everything else uses the filename stem.

The RFC lifecycle fields live here too ([Change lifecycle](../decisions/change-lifecycle.md)): `rfc_state` has four values (`draft`, `accepted`, `implemented`, `rejected`); `RFC_STATE_TRANSITIONS` is the single table of legal next states. `resolved_by` is required for both `accepted` and `implemented`. `affects` declares the component ids a proposal intends to change (`[]` means intentionally none) and `direction` marks foundation impact as `extends` or `revises`.

Stable ADRs can own retirement tombstones through `retires`
([Change lifecycle](../decisions/change-lifecycle.md)). Each entry has a
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

The write side lives in `src/irminsul/frontmatter_edit.py`: round-trip helpers (`set_value`, `add_to_list`, `remove_inventory_item`, and the `setter` and `list_adder` fix factories) that the deterministic [fix](new-list-regen.md) actions share so every rewrite re-emits keys in canonical order, leaves the body untouched, and is idempotent.


## Scope & Limitations

Frontmatter parsing enforces structural field correctness only — it does not evaluate prose style or content quality. It does not validate `describes:` glob patterns (that is the `globs` check). Unknown top-level fields are accepted (`extra="allow"`) and not validated, apart from the misspelled-field error above; entries under `claims`, `inventory`, `retires`, and `required_updates` reject unknown keys.
