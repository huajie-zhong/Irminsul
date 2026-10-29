---
id: derive-facts-and-leave-meaning-to-the-reader
title: Derive facts and leave meaning to the reader
status: stable
describes: []
summary: Facts reconstructable from code are derived on demand and never committed, docs curate intent that inventories keep honest, and prose is selected for a reader by facts alone, never by a word list.
governs:
  - src/irminsul/listing/review.py
  - "!src/irminsul/listing/review.py#_governing_claims_over_changed_code"
  - "!src/irminsul/listing/review.py#_removed_sentences"
  - "!src/irminsul/listing/review.py#_moved_file_sentences"
  - src/irminsul/checks/inventory_drift.py
  - src/irminsul/checks/foundation_readiness.py
  - src/irminsul/git/blame.py
retires:
  - id: claim-provenance-prose-codes
    kind: concept
    matches:
      - risky-prose-unclaimed
      - structured-section-unclaimed
      - negated-claim
    guidance: Declare a sentence that must stay true as a claim with evidence; `claim-provenance` checks the evidence exists and reports when it changes.
  - id: reality-check
    kind: concept
    matches:
      - reality/speculative-language
      - reality/history-narration
      - reality/unrecorded-decision
      - forbid_speculation
    guidance: Plans belong in an RFC and history in a decision record; `irminsul list review --changed` hands every edited sentence to the reader.
  - id: glossary-redefinition
    kind: concept
    matches:
      - redefined-term
    guidance: Link the term's glossary entry rather than defining it again; `glossary-discipline` still reports forbidden synonyms, unused entries and unlinked uses.
  - id: section-reference-check
    kind: concept
    matches:
      - section-reference
    guidance: Link the section you mean; `links` reports a link whose heading anchor is missing.
  - id: terminology-overload-check
    kind: concept
    matches:
      - terminology-overload
      - terminology_overload
    guidance: Declare a banned spelling as a glossary `forbidden_synonyms` entry, which `glossary-discipline` reports.
  - id: liar-check
    kind: concept
    matches:
      - liar
      - prose_named
    guidance: Name the commands a doc means in code spans; `code-references` reports one that no longer exists, and an `inventory:` entry checks a curated list against the code.
---

# Derive facts and leave meaning to the reader

## Status

Accepted, 2026-10-28.

## Context

A list that can be rebuilt from code, such as commands, options, endpoints, exports or
environment variables, goes stale the moment it is committed, as a generated page or as prose,
yet docs still need to say which of those things matter and why. Irminsul is good at what can be
proven: a link resolves, a file has an owner, evidence changed after the doc. Matching words
cannot judge what a sentence means: a rule that warns on "block" without a cited claim fires on
"Wrap the example in a code block." and is silent on "CI will reject the PR." The agent reading
the output judges meaning better than any list; what it cannot cheaply know is which sentences
its change connects to.

## Decision

- **Derive on demand.** Static extractors, which never import the target's code, back
  `irminsul surface <kind>`, and nothing derived is committed. The agent manifest is the one
  generated file.
- **Curate intent in `inventory:`.** A doc lists in `items` the part of a surface it calls out,
  and `inventory-drift` reports a listed identity the code no longer has. `complete: true` also
  reports a live identity neither listed nor in `omit`; `explained_in: self` or `any` requires
  every live identity to be named in a code span of the declaring doc or of any stable doc, with
  `foreign` naming other tools' identities. Config keys, check names and frontmatter fields are
  surfaces declared as `surface.rules`, and the MCP tool set is a watched surface, for its own
  consistency rather than parity with the CLI.
- **Irminsul selects by facts; the reader judges meaning.** No hardcoded list of words or
  phrases raises a finding or decides which sentences a reader sees. A list a project declares
  as its own rule, such as a spelling its glossary forbids, judges no meaning. The checks and
  settings that judged prose by words are this record's `retires:` entries. A scaffold prompt
  carries the `<!-- irminsul:placeholder -->` marker: `foundation-readiness` reports a doc that
  still has one, and `seed` replaces only marked text.
- **A doc is re-asked through its connections to code.** A sentence that explains code names it
  in a code span, anchors its paragraph, or rests on a claim with evidence; the root `AGENTS.md`
  loop says so.
- **`list review` routes semantic checking and never decides truth.** It reads live docs, the
  `## Decision` of decision records, and the guidance files. With a change, given by `--changed`
  or `--base-ref`, it queues each sentence the change added, reworded or deleted, each claim
  other than a report whose evidence it touched, each sentence an old owner keeps about a file moved to another doc,
  and each `summary:` left behind a rewritten body. Without one it queues sentences that name
  code. An item's markers name the fact that selected it, and the output defines each once.
- **Freshness marks what to read.** Without a change, an item is marked only when a line of the
  definition it names, a function's or class's range, a surface identity's declaring line, or a
  whole file for a path, changed after the doc's last commit, by one `git blame` per file;
  uncommitted lines count. Only marked items show unless `--all` is given, and JSON reports both
  counts. A `context` packet lists the claims that cite its paths as evidence, not this queue.
- **`foreign` is deleted** (accepted, not yet implemented). A span that invokes this project's
  program stays `inventory-drift/unknown-mention`, certain; a bare flag no program precedes is
  `inventory-drift/unattributed-mention`, a hint an ignore comment on its line answers. This
  replaces "with `foreign` naming other tools' identities" above.

## Alternatives Considered

- **Generated reference pages verified in CI.** Rejected: they name everything, explain nothing,
  and drift between regenerations.
- **A parity check between MCP tools and CLI commands.** Rejected: they differ by design.
- **Count plain-prose mentions as explanation.** Rejected: identifiers such as `tags` collide
  with ordinary words.
- **One finding per assertion.** Rejected: an ordered queue is workable where hundreds of
  findings are not.
- **Better word lists, or lists kept as labels.** Rejected: each fix moves the miss, and a label
  still filters what the reader sees.
- **Ask a model.** Rejected: no check calls one; the reader is the model.
- **Mark by file, store a reviewed stamp, or run `git log -L` per reference.** Rejected: a busy
  file marks everything, the queue is derived on every call, and blame answers a whole file in
  one process.

## Consequences

- Surfaces cannot drift in committed form.
- Enforcement prose without evidence does not warn; it reaches a reader when edited, and a
  sentence that must stay true is declared as a claim. Deleting a section queues each sentence.
- **Known limitation.** A doc is re-asked only through what it owns through `describes`, its
  claims, its anchors and the code it names. One connection makes a doc look tied to code while
  its other sections rot unseen, and a sentence about code it neither names nor anchors is never
  re-asked when that code changes; `--all` shows the unmarked rest. Finer rules, per section and
  per changed definition, are deferred.

## Changes

- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  `foreign` goes, and a bare flag no program precedes becomes a hint.
- 2026-10-29: Accepted [A change re-asks the sentences that name its code](../rfcs/a-change-re-asks-the-sentences-that-name-its-code.md):
  `list review --changed` queues each sentence naming code the change touched.
