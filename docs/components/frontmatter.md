---
id: frontmatter
title: Frontmatter
status: stable
summary: Per-doc YAML frontmatter parser/validator.
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
---

# Frontmatter

Every [doc atom](../GLOSSARY.md#doc-atom) carries a YAML frontmatter block, whose canonical field surface is defined by `DocFrontmatter` in `src/irminsul/frontmatter.py`. `parse_doc()` returns a `ParsedDoc` or a `ParseFailure`; the [DocGraph](docgraph.md) collects the failures and the [frontmatter check](checks.md) translates them to findings.

`extra="allow"` is intentional — projects extend the schema with their own fields — so strictness comes from validating the canonical ones. Two kinds of unknown key are errors anyway, because a key that does nothing reads as if it works: one that reads as a misspelled canonical field the doc does not set, such as `desribes` for `describes`, which leaves the field it meant to set empty so every check that reads it goes quiet; and one Irminsul once read, reported as `frontmatter/retired-field` with what replaced it. A project's own key needs a name that cannot be mistaken for a field.

Every doc carries a one-sentence `summary:`, which a draft may omit with a warning. YAML is read as 1.2, so `id: no` and `tags: [on]` hold the strings `no` and `on`, and `0123` is the number 123, not an octal. `read_frontmatter()` is the one reader of the block and `entry_line()` the one finder of an entry's file line, which [refs](refs.md) and the `doc-refs` check point at; their docstrings say what each refuses.

Two fields name test paths and mean different things. `recommended_tests:` is what an agent editing this component should run — a recommendation, not an inventory of what covers it or evidence that anything ran, so several docs may recommend one shared test; unset, it defaults to the tests the doc owns. `owns_tests:` is maintenance ownership of a test implementation file, singular per file and written as exact paths, enforced by `test-ownership`.

An `inventory:` entry names a surface `kind` and optional `source` glob, lists the `items` the doc calls out, and may opt into watching: `complete` compares the live surface against `items` plus `omit`, and `explained_in` (`self` or `any`) requires every live identity outside `omit` to be named in a code span of this doc or of any stable live doc. For a `cli-options` entry, a flag-shaped code span naming no live option is reported unless listed in `foreign` — but only in a span this project's inventory is entitled to judge: one that opens by invoking another program names that program's options, not ours.

A `claims:` entry pairs an assertion with the `evidence` it rests on and a `relation` saying who wins when the two disagree ([authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)). An omitted relation means `review-on-divergence`, because nothing should infer an authority nobody declared, and a `planned` claim cannot be `follows-evidence`. A claim's `pinned` maps each evidence path to the hash it had when someone last re-read the claim against it; [`anchors --re-pin`](anchors.md) writes it, never a hand.

The RFC lifecycle fields live here too ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): `rfc_state` has four values, `RFC_STATE_TRANSITIONS` is the single table of legal next states, and the named sets beside it are what a reader asks instead of listing states inline. `affects` declares the component ids a proposal intends to change (`[]` means intentionally none), `direction` marks foundation impact as `extends` or `revises`, and `target_decision_date` (`YYYY-MM-DD`) on a draft RFC makes `rfc-follow-through` warn once it has passed. `weight` is `small` or `large` and says how much of an RFC's owner's part its owner reads ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)); `rfc-structure` is its only reader, and the field is a plain string so that a value other than those two is reported on the RFC instead of failing the parse and taking the RFC out of the graph.

Stable ADRs own retirement tombstones through `retires` ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): each entry has an `id`, a `kind` of `cli-command` or `concept`, exact `matches` and `guidance`, and a `cli-command` also names `surface_identity`, the identity `irminsul surface cli` prints without the executable name.

The write side lives in `src/irminsul/frontmatter_edit.py`: round-trip helpers (`set_value`, `add_to_list`, `remove_inventory_item`, and the `setter` and `list_adder` fix factories) that the deterministic [fix](new-list-regen.md) actions share so every rewrite re-emits keys in canonical order, leaves the body untouched, and is idempotent. A rewrite keeps the doc's own list layout, so a one-value edit shows in a diff as one line, but the writer applies one layout to a whole block, so a doc that mixes them comes back indented.

## Scope & Limitations

Frontmatter parsing enforces structural field correctness only — it does not evaluate prose style or content quality. It does not validate `describes:` glob patterns (that is the `globs` check). Unknown top-level fields are accepted (`extra="allow"`) and not validated, apart from the misspelled-field and retired-field errors above; entries under `claims`, `inventory`, `retires`, and `required_updates` reject unknown keys other than a retired one.
