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
    guidance: Plans belong in an RFC and history in a decision record; `irminsul list review --written` hands every edited sentence to whoever reviews the change.
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
  `## Decision` of decision records, and the guidance files. A change has two lists, one per
  run. `--changed`, which `--base-ref` alone also means, queues what the change left as it was
  and may have made stale: each sentence whose code span names a function or class the
  change touched, each claim other than a report whose evidence it touched, each sentence an
  old owner keeps about a file moved to another doc, and each `summary:` left behind a
  rewritten body. `--written` lists what the change wrote, for whoever reviews it: each
  sentence it added, reworded or deleted, and nothing else. Both name a change alike, the
  uncommitted work alone or the range from the merge base with `--base-ref`, and the two
  together exit 2. Without a change it queues sentences that name code. An item's markers name
  the fact that selected it, and the output defines each once.
- **A change re-asks the sentences that name its code.** In every file the queue reads, the
  change's own or not, a sentence whose code span names a function or class the change
  edited, renamed or deleted is queued, marked `names-changed-code`, with the name and the
  change's file and line. What a span names is what freshness says it names. A function or class
  is touched when its own lines, its decorators included, differ between the merge base and
  where the change ends, the working tree, or `HEAD` under `--committed-only`; one the change
  removed or renamed is found in the merge base's text. Nothing else a span can name is paired
  with a change: not a command, an option, an environment variable or a path, which too many
  sentences name for too many reasons. What already answers for those stays: `code-references`
  reports a command or option the code no longer has, and `inventory-drift` a doc's list that
  misses one the code gained. A function or class is one a reader reads with its lines, in
  Python, TypeScript, JavaScript, Go or Rust, and one of a language no reader reads is paired
  with nothing. An export is no second name beside its definition: a span that names one names
  the definition of that name in the export's language. A sentence the change did not write is queued
  in `--changed` under the marker, and one the change itself wrote carries the marker on its one
  `edited` item in `--written`. `list review` alone lists these sentences, and
  `context --after-edit` none of them. Whether a queued sentence still holds is
  meaning, so none of this is a finding.
- **Freshness marks what to read.** Without a change, an item is marked only when a line of the
  definition it names, a function's or class's range, a surface identity's declaring line, or a
  whole file for a path, changed after the doc's last commit, by one `git blame` per file;
  uncommitted lines count. Only marked items show unless `--all` is given, and JSON reports both
  counts. A `context` packet lists the claims that cite its paths as evidence and the docs that
  name code in them, each with a count of its sentences, not this queue.
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
- Enforcement prose without evidence does not warn; it reaches the change's reviewer when
  edited, and a sentence that must stay true is declared as a claim. Deleting a section lists
  each sentence under `--written`.
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
- 2026-11-25: Accepted [The change queue asks about what the change did not write](../rfcs/the-change-queue-asks-about-what-the-change-did-not-write.md):
  `list review --changed` drops the sentences a change wrote or deleted, and `list review --written`
  lists them for the change's reviewer.
- 2026-11-26: The re-ask of named code is implemented as the owner amended it that day, after
  a first build that paired every kind of name was measured and a review of the second:
  `list review --changed` queues each sentence whose code span names a Python function or class
  the change edited, renamed or deleted, touched when its own lines, decorators included, differ
  between the merge base and where the change ends, and pairs no command, option, environment
  variable, path or other language's definition with a change; a `context` packet names the
  docs that name code in its paths, so the sentence on what a packet lists names them beside the
  claims.
- 2026-11-26: The split of a change's queue is implemented: `list review --changed` and
  `--base-ref` alone queue what the change left as it was and may have made stale, `list
  review --written` lists the sentences it added, reworded or deleted, the two together exit 2,
  and the JSON of each names its list. A sentence the change wrote carries
  `names-changed-code` on its `edited` item in `--written`, and the retired concept's guidance
  and the Consequences name `--written`.
- 2026-11-27: The readers of TypeScript, JavaScript, Go and Rust are implemented, so the change
  queue pairs a function or class of any language a reader reads, as
  [Each language reads its code through one interface](../rfcs/each-language-reads-its-code-through-one-interface.md)
  decides when it lifts the Python-only rule of 2026-11-26. A span that names an export names
  its definition, with its lines.
