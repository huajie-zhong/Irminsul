---
id: a-change-re-asks-the-sentences-that-name-its-code
title: "A change re-asks the sentences that name its code"
status: stable
describes: []
rfc_state: accepted
affects:
  - new-list-regen
  - context
  - init
resolved_by: docs/decisions/derive-facts-and-leave-meaning-to-the-reader.md
summary: When a change edits code, the review queue asks again about every sentence that names that code in a code span, and `context <path>` lists those sentences before the edit, so an agent finds the docs a change makes stale without searching for them.
required_updates: []
weight: large
---

# A change re-asks the sentences that name its code

## Summary

An agent that changes code is shown every sentence, in any doc, that names that code in a
code span: before the edit, in the packet `context` prints for the file, and after it, in the
review queue. Today a sentence is asked about again only when its own doc owns the code,
anchors it or claims it, so a guide that names a command is never asked about when the
command changes, although the loop tells agents a code span is enough. Three decisions, all
answered.

## Problem

Two fresh agents, working in a small adopted project on 2026-10-29, each hit this.

Agent B added a JSON option to the project's list command. The usage guide names that
command and says what it does, the README names the environment variables, and neither doc
owns the code. The packet for the command's file said no doc owns it; after the edit the
review queue held nothing and the change validation passed. The agent found the two docs by
searching the text.

Agent C renamed a method that a component doc names in three sentences. The queue stayed
empty until the agent had already edited those sentences.

The loop in `AGENTS.md` says a doc is asked about code through a code span, an anchor or a
claim. The queue the loop uses honours only the last two.

## How it works

The review queue already pairs each code span with the code it names: a function's lines, the
line that declares a command, option or environment variable, or a file. Without a change it
uses that pairing to mark sentences whose code moved since their doc was committed. With a
change it will use the same pairing against the change's own lines: a sentence is queued when
the code it names was edited, renamed or deleted by the change. A word that names nothing in
the code pairs with nothing, so this is not a text search.

Before an edit, the packet for a file gains a list of the sentences elsewhere that name code
in it, so the agent knows which docs to read before changing anything.

It stays a reading list. Nothing new blocks a gate; a sentence that is still right needs no
answer.

## Cost and risk

A run with a change pairs every code span in the docs, the work the queue already does without
one: on this repository that run takes 8 seconds with its per-file history lookups, and a
change run takes 2. The packet for a file, 1 second today, would do the pairing too, so it
grows unless it is asked for. A common word that happens to name a command, such as `add`,
queues sentences about something else; how the pairing chooses is unchanged, and a qualified
name such as `Ledger.add` avoids it.

## Decisions

Answered by the owner on 2026-10-29, each as recommended: queue them; the packet lists them
always, capped; a sentence naming a whole file is asked on any edit to it.

1. **Queue the sentences that name changed code** in `list review --changed` and
   `context --after-edit`. Recommended: yes; it is the connection the loop already promises.
2. **The packet's list of sentences naming a file**: always, or only when asked for. Always
   puts it where the agent needs it, at a few seconds' cost per call; on request keeps the
   packet fast and relies on the agent asking. Recommended: always, capped like the packet's
   other lists, with the count of the rest.
3. **A sentence that names a whole file** is queued on any edit to that file, or only when the
   file is renamed or deleted. Any edit is the honest reading of "names this code" but noisy
   for a large file; rename and delete only is quiet but misses a file whose content changed
   meaning. Recommended: any edit, since a sentence about a whole file is usually about what
   the file is for.

## Design detail

- **Today's rule.** `derive-facts-and-leave-meaning-to-the-reader` decides the queue: with a
  change it queues the sentences the change added, reworded or deleted, the claims whose
  evidence it touched, an old owner's sentences about a moved file, and stale summaries;
  without one, sentences naming code, marked by freshness. This [RFC](../GLOSSARY.md#rfc) adds a fifth item to the
  first list. The freshness rule's notion of what a sentence names is reused as it stands
  (`listing/review.py`, `irminsul.binding`, `CodeResolver`, `changed_after`).
- **Touched.** A function or class is touched when the change's diff alters a line in its
  range; a command, option or environment variable when its declaring line, or the function
  that declares it, is altered or removed; a file when the change edits, renames or deletes it.
  The ranges come from the merge base's text for code the change removed or renamed, so a
  sentence naming `Ledger.remove` is queued by the rename that removes it, and from the
  working tree's for the rest. The diff's line ranges come from the same reading `_touches`
  uses for doc lines.
- **Marker.** A new marker, `names-changed-code`, defined once in the output like the others,
  naming the code and the change's file and line.
- **Packet.** `context <path>` gains `named_by`: each sentence, in a live doc, a decision
  record's Decision or a guidance file, whose code span pairs with code in that path, as
  `path:line` and the span. Capped as the packet caps its other lists; JSON carries all.
- **The loop's wording.** Step 4 of the root `AGENTS.md` and its template
  `src/irminsul/init/scaffolds/AGENTS.md.j2` say "Both also queue the claims whose evidence you
  touched"; they gain "and the sentences anywhere that name code you changed". The test that
  keeps the two equal covers it.
- **Governing records.** The queue's rule is a Decision of
  `derive-facts-and-leave-meaning-to-the-reader`; the packet's contents of
  `agents-get-stateless-read-only-queries-and-one-written-loop`. Both gain a bullet and a dated
  Changes item when this is accepted.
- **Not chosen.** A `refs` for code names: the retired `refs --symbol` matched `describes`
  globs and claim evidence, which `context <path>` already answers, and a text search is what
  `grep` does. Making a sentence that names changed code a finding: whether it is still right
  is meaning, which no check knows.
- **Evidence.** The scenario logs are in the lead's dogfood notes of 2026-10-29: agents B
  (`list --json`, `LEDGER_DATE_FORMAT`) and C (`Ledger.remove` to `Ledger.delete`) each found
  the stale docs by grep, and C's `list review --doc` without a change did list the seven
  sentences that `--changed` left out.

## Requirements

### Requirement: A change queues the sentences that name its code
ID: change-queues-sentences-naming-its-code
Provenance: code

With a change, `list review` SHALL queue each sentence, in a live doc, a decision record's
Decision or a guidance file, whose code span names a function, class, command, option,
environment variable or file that the change edited, renamed or deleted, marked
`names-changed-code`.

#### Scenario: An option added to a command
- **WHEN** a change adds an option to the `list` command, and the usage guide says what `` `ledger list` `` does in a sentence the change does not edit
- **THEN** `list review --changed` queues that sentence, marked `names-changed-code`

#### Scenario: A renamed method
- **WHEN** a change renames `Ledger.remove` to `Ledger.delete`, and a component doc names `` `Ledger.remove` `` in a sentence the change does not edit
- **THEN** `list review --changed` queues that sentence

#### Scenario: Code the change did not touch
- **WHEN** a change edits only the `list` command, and a sentence names the `report` command
- **THEN** `list review --changed` does not queue that sentence for `names-changed-code`

### Requirement: The packet lists the sentences naming a file
ID: packet-lists-sentences-naming-a-file
Provenance: code

`irminsul context <path>` SHALL list, under `named_by`, each sentence in a live doc, a
decision record's Decision or a guidance file whose code span names code in that path.

#### Scenario: A guide names a command
- **WHEN** `irminsul context src/ledger/cli.py` runs and the usage guide names `` `ledger list` ``
- **THEN** the packet's `named_by` includes that sentence's path and line

## Tasks

- `T1` Read the change's line ranges for source files and pair code spans against the merge base and the working tree. (req: change-queues-sentences-naming-its-code)
- `T2` Queue the paired sentences with the `names-changed-code` marker. (req: change-queues-sentences-naming-its-code)
- `T3` Add `named_by` to the packet. (req: packet-lists-sentences-naming-a-file)
- `T4` Say it in step 4 of the root `AGENTS.md` and its template. (component: init)
- `T5` State the rules in the two governing records with dated Changes items. (component: context)

## Resolution

Accepted by the owner on 2026-10-29, with the answers recorded under Decisions, and resolved by [Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md), whose Changes item records it. [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) records its part too. Each rule joins its record's Decision with the implementation, as an edit in place once decision records are living topics.
