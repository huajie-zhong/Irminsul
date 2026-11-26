---
id: the-change-queue-asks-about-what-the-change-did-not-write
title: "The change queue asks about what the change did not write"
status: stable
describes: []
rfc_state: accepted
affects:
  - new-list-regen
  - cli
  - init
resolved_by: docs/decisions/derive-facts-and-leave-meaning-to-the-reader.md
summary: "`list review --changed` stops listing the sentences a change itself wrote or deleted and keeps the sentences the change left as they were and may have made stale; the written sentences move to `list review --written`."
required_updates: []
weight: large
---

# The change queue asks about what the change did not write

## Summary

After a change, the review queue asks one question: you changed this, so does that still
hold? It lists only sentences the change left as they were and may have made stale. The
sentences the change itself wrote or deleted leave that list and get one of their own, for
whoever reviews the change. Measured on three merged pull requests and two commits, two thirds
of the queue was the change's own text. Three decisions, all answered.

## Problem

Take the pull request that closed the dogfood gaps on 2026-10-31. Its queue held 48 items: 29
sentences that pull request had just written, 8 summaries of docs it had edited, and 11 claims
resting on code it had changed. An agent working through that list re-reads its own new text
29 times to reach the 19 items that ask whether something older still holds.

Across the three pull requests and two commits the queue held 189 items, and the change
itself had written or deleted 126 of them. In those same ranges the code changes made eight
older sentences false, and none of the eight was in a queue.

This proposal does not find those eight. Another accepted proposal queues the ones that name
the changed code. This one makes the list short enough that what it holds is read.

## How it works

**One list per question.** The queue of a change keeps every item about a sentence the change
did not write: a claim whose evidence the change touched, the summary of a doc whose body it
edited, a sentence a file's previous owner still has about a file that moved. What other
accepted proposals add to that list stays in it.

**The written sentences get a list of their own**, under a new flag. It holds each sentence
the change added or reworded, beside the sentence it replaced and any name in it that binds
to no code, and each sentence the change deleted. Nothing is lost: the two lists together are
today's queue.

**Who reads which.** The author's loop asks for the first list. Decision 3 settles who reads
the second.

**What it leaves out.** It judges no sentence, and it does not make the first list find more
than it finds today.

## Cost and risk

A flag, a split of what one function returns, and new wording in the loop and in four decision
records. The report's version number rises, so a script that reads the JSON must expect the
shorter list.

The risk is a wrong new sentence that nobody re-reads. The pull request above wrote three
sentences it corrected before merging, and two of the three name no code, so only a second
reading catches them. The loop is scaffolded for every adopter, and nothing in it today
describes a reviewer. So the protocol asks a change with no second reader to have its author
read the written list once, before the pull request.

## Decisions

Answered by the owner on 2026-11-25:

1. **The sentences a change wrote or deleted leave its queue.** What that writing may have
   made stale stays in it: the summary of the doc it is in, and the claims that cite that doc
   as evidence.
2. **They stay reachable under a flag of their own**, for whoever reviews the change, its docs
   included.
3. **A reviewer's step in the agent protocol names the written list, and the author's loop
   names only the queue.** A change with no second reader has its author read the written
   list once, before opening the pull request, not after every edit.

## Design detail

- **Today.** With a change, `build_review` in `src/irminsul/listing/review.py` returns six
  kinds of item: `edited`, for each sentence on a changed line that the base did not have,
  with `unbound-name` where a name in it binds to nothing; `removed-sentence`;
  `governing-claim`, for each claim other than a report whose evidence the change touched;
  `stale-summary`; `moved-file`; and, since the RFC that re-asks named code landed,
  `names-changed-code`.
- **The rule, by marker.** `--changed` holds no `edited` and no `removed-sentence` item, and
  every other item as today. `--written` holds those two kinds, built as `--changed` builds
  them today, and nothing else.
- **What an item of `--changed` is about.** A sentence the change left as it was. What selects
  it may still be the change's own edit to that doc: an edit to a body selects the untouched
  `summary:`, and an edit to `describes:` selects the previous owner's sentences. A sentence a
  previous owner keeps about a moved file, reworded in the same change, is therefore
  `moved-file` in one list and `edited` in the other.
- **Flags.** `--written` names a change as `--changed` does: alone it reads the uncommitted
  work, with `--base-ref` the range from the merge base, and `--committed-only` and a missing
  base behave as they do for `--changed` in `src/irminsul/cli.py`. `--base-ref` with neither
  flag keeps meaning `--changed`. `--changed` with `--written` exits 2: one list per run.
- **JSON.** Both lists keep today's shape and gain a `list` key holding `changed` or
  `written`. `REVIEW_VERSION` rises for every caller, the MCP tool `list_docs` included, which
  returns the queue without a change and whose items stay as they are.
- **Unchanged.** `context --after-edit` and `change verify` do not read this queue.
- **Accepted [RFCs](../GLOSSARY.md#rfc) this meets.**
  - `a-change-re-asks-the-sentences-that-name-its-code` queues each sentence that names code
    the change touched, marked `names-changed-code`. With both in force, a sentence the change
    did not write is queued in `--changed` under that marker, and one the change wrote carries
    the marker on its `edited` item in `--written`. Whichever lands second states that.
  - `every-warning-hint-has-an-answer` lists an accepted RFC's open tasks in `--changed`. That
    reminder stays there.
  - `claim-evidence-names-a-part` lists a claim whose evidence the change re-pointed. It stays
    in `--changed`.
- **Records that state today's rule.** Each is edited in place by the implementing change,
  with a dated Changes item.
  - `derive-facts-and-leave-meaning-to-the-reader`: what the queue holds; the guidance of its
    retired concept, "hands every edited sentence to the reader"; and its Consequences, "it
    reaches a reader when edited" and "Deleting a section queues each sentence".
  - `authority-follows-the-kind-of-claim`, which governs `_removed_sentences`: "Deleted prose
    is queued, not blocked".
  - `code-is-named-in-code-spans-and-bound-by-anchors`: an unbound name is marked "under
    `list review --changed`".
  - `agents-get-stateless-read-only-queries-and-one-written-loop`, which governs the loop's
    template: decision 3 adds a procedure to the three the protocol carries.
- **Docs that state it.** `docs/components/new-list-regen.md`, `docs/components/anchors.md`,
  the style guide's sentence on a removed sentence, the README's command table, and the help
  of `list review`.
- **The loop's wording.** Step 4 of the root `AGENTS.md` and its template
  `src/irminsul/init/scaffolds/AGENTS.md.j2` say "`irminsul list review --changed` to re-read
  each sentence you added or changed against the code it names". Step 4 will name what the
  change may have made stale. `docs/guides/agent-protocol.md` and its scaffold gain a
  reviewer's step that names `--written`, and say that a change with no second reader has its
  author read that list once, before the pull request.
- **Tests that assert today's lists.** `tests/test_list_review.py`, `tests/test_binding.py`
  and `tests/test_cli_list.py` read `edited` and `removed-sentence` items under `--changed`.
- **Measured** on 2026-11-25 with the code of `ffa39b4`, by `irminsul list review --changed
  --base-ref <base> --format json` at each head: the ranges `1bf8add..89772e4`,
  `89772e4..dde68e0` and `dde68e0..ffa39b4`, and the commits `460c44c` and `19c75a9` against
  their parents. Of 189 items, 108 were `edited`, 18 `removed-sentence`, 33 `governing-claim`
  and 30 `stale-summary`. The three corrected sentences are in the queue at `db3c929`, before
  the commit that corrected them.
- **Left open.** A doc that links to a doc the change edited is not queued. `irminsul refs`
  lists those docs, and whether an edit should ask about them is a later change.
- **Not chosen.** An author's loop that names both lists after every edit: the author would
  still re-read its own text on each run. Ordering the queue so the items the author did not write come first: the
  reader is a model, which reads the whole list, so order shortens nothing. Keeping only the
  written sentences that name code: it splits one kind of item by what the tool can add to it,
  not by what the reader is asked. Folding the written sentences into a count per doc: a count
  asks nothing.

## Requirements

### Requirement: A change's queue holds no sentence the change wrote
ID: change-queue-holds-no-written-sentence
Provenance: code

`list review --changed` SHALL queue no `edited` item and no `removed-sentence` item, and SHALL
queue every other item as it does without this change.

#### Scenario: A reworded sentence
- **WHEN** a change rewords one sentence of a doc and `list review --changed` runs
- **THEN** the queue holds that doc's `stale-summary` item and no `edited` item

#### Scenario: Evidence touched
- **WHEN** a change edits a file that a claim other than a report cites as evidence, and edits no doc
- **THEN** the queue holds that claim as a `governing-claim` item

### Requirement: The written sentences are their own list
ID: written-sentences-are-their-own-list
Provenance: code

`list review --written` SHALL queue the `edited` and `removed-sentence` items of the change,
each as `list review --changed` built it before this change, and SHALL queue nothing else.

#### Scenario: A reworded sentence under the flag
- **WHEN** a change rewords one sentence of a doc and `list review --written` runs
- **THEN** the queue holds one `edited` item whose `was` is the sentence it replaced

#### Scenario: A deleted sentence under the flag
- **WHEN** a change deletes one sentence of a doc and `list review --written` runs
- **THEN** the queue holds that sentence as a `removed-sentence` item

### Requirement: One list per run
ID: one-list-per-run
Provenance: code

`list review` given `--changed` and `--written` together SHALL exit 2 and print no queue, and
given `--base-ref` with neither SHALL print the list `--changed` prints.

#### Scenario: Both flags
- **WHEN** `list review --changed --written` runs
- **THEN** it exits 2 and names the two flags

## Tasks

- `T1` Split the items of a change in `build_review` into the two lists. (req: change-queue-holds-no-written-sentence)
- `T2` Add `--written`, the `list` key and the raised report version, and move the tests that read `edited` and `removed-sentence` items to it. (req: written-sentences-are-their-own-list)
- `T3` Refuse the two flags together and keep `--base-ref` alone on `--changed`. (req: one-list-per-run)
- `T4` Reword step 4 of the root `AGENTS.md` and its template, and add the reviewer's step and the rule for a change with no second reader to the agent protocol and its scaffold. (component: init)
- `T5` State the rule in the four records with a dated Changes item each, and in the docs listed under Design detail. (component: new-list-regen)

## Resolution

Accepted by the owner on 2026-11-25, with the answers recorded under Decisions, and resolved by [Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md), whose Changes item records it. [Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md), [Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md) and [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) record their parts too. Each rule joins its record's Decision with the implementation, as an edit in place.
