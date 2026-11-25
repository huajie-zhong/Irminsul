---
id: the-change-queue-asks-about-what-the-change-did-not-write
title: "The change queue asks about what the change did not write"
status: draft
summary: "`list review --changed` queues only what a change may have made stale and did not itself write, and the sentences the change wrote move to `list review --written`, which the change's reviewer reads."
describes: []
rfc_state: draft
affects:
  - new-list-regen
  - init
weight: small
---

# The change queue asks about what the change did not write

## Summary

The review queue of a change becomes one kind of reminder: you changed this, so check that
that still holds. It keeps the claims, summaries and sentences the change did not write and may
have made stale. The sentences the change itself added, reworded or deleted leave it, because
they are the change's own diff, which its reviewer reads. Measured on three merged pull
requests and two commits, they were 126 of the queue's 189 items. Three decisions, none
answered yet.

## Decisions

1. **What the change wrote leaves `list review --changed`.** Kept, the author re-reads its own
   new text in a list three times as long as the part that asks about staleness. Dropped, a
   wrong new sentence is caught by the reviewer or not at all. Recommended: drop it, since a
   list that asks one question gets an answer per item, and a fresh reviewer reads the diff.
2. **The written sentences stay reachable under `--written`**, or go altogether. Under a flag
   the reviewer still gets each new sentence beside the code it names, and each name that
   binds to nothing. Gone, the diff is all there is. Recommended: `--written`.
3. **The author's loop stops asking for the written sentences.** Step 4 of the root
   `AGENTS.md` asks the author to re-read each sentence it added or changed. It would ask for
   `--changed` alone, and the reviewer's step would name `--written`. Recommended: yes, given a
   fresh reviewer on every pull request.

## Design detail

- **Today.** `derive-facts-and-leave-meaning-to-the-reader` decides the queue: with a change it
  holds each sentence the change added, reworded or deleted, each claim whose evidence it
  touched, an old owner's sentences about a moved file, and each `summary:` left behind an
  edited body. The first group is selected by the change's own edit to a doc; the others by an
  edit somewhere else.
- **The rule.** `--changed` and `--base-ref` queue the second group alone: `governing-claim`,
  `moved-file` and `stale-summary` items, and the `names-changed-code` items of
  `a-change-re-asks-the-sentences-that-name-its-code` once that lands. `--written` queues the
  first group alone: `edited` items with their `was` and `unbound-name`, and `removed-sentence`
  items. It reads the same change, takes the same `--base-ref` and `--committed-only`, and is
  not combined with `--changed`: each flag answers one question. A sentence the change wrote
  that also names code the change touched is the change's own, so `--written` holds it.
- **JSON.** The report version rises, since a `--changed` report no longer holds `edited` or
  `removed-sentence` items. The MCP tool `list_docs` returns the queue without a change, which
  this leaves as it is.
- **The loop's wording.** Step 4 of the root `AGENTS.md` and its template
  `src/irminsul/init/scaffolds/AGENTS.md.j2` say "`irminsul list review --changed` to re-read
  each sentence you added or changed against the code it names". They would say what the change
  may have made stale, and `docs/guides/agent-protocol.md` with its scaffold would name
  `--written` for the reviewer of a change.
- **Measured** on 2026-11-25, with that day's code, over the three pull requests merged on
  2026-10-30 and 2026-10-31 and two single commits: 189 items, of them 108 `edited`, 18
  `removed-sentence`, 33 `governing-claim` and 30 `stale-summary`. Eight sentences those pull
  requests made false and did not edit were in no queue, so the list was long and still did not
  hold what had gone stale.
- **The risk.** One of those pull requests wrote three sentences it corrected before merging,
  and two of the three name no code. Nothing but a second reading catches those, in either
  list, so decision 3 rests on a reviewer who was not the author.
- **`unbound-name`** tells a writer that a new sentence names nothing the resolver binds. It
  moves with the `edited` items, so the reviewer sees it and the author no longer does unless
  it runs `--written`.
- **Governing record.** `derive-facts-and-leave-meaning-to-the-reader`, whose Decision lists
  what the queue holds.
- **Not chosen.** Ordering the queue so the items the author did not write come first: the
  reader is a model, which reads the whole list, so order shortens nothing. Keeping only the
  written sentences that name code: it splits one kind of item by what the tool can add to it,
  not by what the reader is asked. Folding the written sentences into a count per doc: a count
  asks nothing.

## Requirements

### Requirement: A change queues only what it did not write
ID: change-queues-only-what-it-did-not-write
Provenance: code

`list review --changed` SHALL queue no sentence the change added, reworded or deleted, and
SHALL queue each claim whose evidence the change touched, each sentence a previous owner keeps
about a file the change moved, and each `summary:` left unchanged by an edit to its body.

#### Scenario: A reworded sentence
- **WHEN** a change rewords one sentence of a doc and `list review --changed` runs
- **THEN** the queue holds that doc's `stale-summary` item and no `edited` item

#### Scenario: Evidence touched
- **WHEN** a change edits a file that a claim cites as evidence, and edits no doc
- **THEN** the queue holds that claim as a `governing-claim` item

### Requirement: The written sentences are their own list
ID: written-sentences-are-their-own-list
Provenance: code

`list review --written` SHALL queue each sentence the change added or reworded, with the
sentence it replaced and each name in it that binds to nothing, and each sentence the change
deleted, and SHALL queue nothing else.

#### Scenario: A reworded sentence under the flag
- **WHEN** a change rewords one sentence of a doc and `list review --written` runs
- **THEN** the queue holds one `edited` item whose `was` is the sentence it replaced

## Tasks

- `T1` Split the items of a change in `build_review` into the two lists and add `--written`. (req: change-queues-only-what-it-did-not-write)
- `T2` Carry the choice in the JSON, with the report version raised. (req: written-sentences-are-their-own-list)
- `T3` Reword step 4 of the root `AGENTS.md` and its template, and name `--written` in the agent protocol and its scaffold. (component: init)
- `T4` State the rule in the governing record with a dated Changes item, and update `docs/components/new-list-regen.md`. (component: new-list-regen)
