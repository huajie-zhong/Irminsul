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
  - cli
  - mcp-server
resolved_by: docs/decisions/derive-facts-and-leave-meaning-to-the-reader.md
summary: When a change edits a function or a class, the review queue asks again about every sentence that names it in a code span, and `context <path>` names the docs that name code in a file before the edit, so an agent finds the docs a change makes stale without searching for them.
required_updates: []
weight: large
---

# A change re-asks the sentences that name its code

## Summary

An agent that changes a function or a class is shown every sentence, in any doc, that names
it in a code span, in the review queue after the edit. Before an edit, the packet `context`
prints for a file names every doc that names code in that file. Today a sentence is asked
about again only when its own doc owns the code, anchors it or claims it, so a guide that
names a function is never asked about when the function changes. Five decisions, all
answered: three were changed and two added on 2026-11-26, after the first build was measured.

## Problem

Two fresh agents, working in a small adopted project on 2026-10-29, each hit this.

Agent B added a JSON option to the project's list command. The usage guide names that
command and says what it does, the README names the environment variables, and neither doc
owns the code. The packet for the command's file said no doc owns it; after the edit the
review queue held nothing and the change validation passed. The agent found the two docs by
searching the text.

Agent C renamed a method that a component doc names in three sentences. The queue stayed
empty until the agent had already edited those sentences.

The first build paired every kind of name with a change, and was measured on four real
changes of this repository. On one pull request the queue grew from 48 items to 214. Of ten
new items sampled, none was about what the change had altered: a command is named in
hundreds of sentences, and a three-line edit inside the function that declares it queued
them all.

## How it works

**After an edit, the queue pairs functions and classes.** A sentence is queued when a
function or class it names in a code span was edited, renamed or deleted by the change. A
word that names nothing in the code pairs with nothing, so this is not a text search.

**A command, an option, an environment variable and a file are not paired with a change.**
Too many sentences name them for too many reasons. What already answers for them stays: a
sentence naming a command or option the code no longer has fails the gate, a doc that lists
a command's options is checked against them, and a sentence about behaviour can be anchored
to the test that asserts it.

**Before an edit, the packet names docs, not sentences.** For each file it lists the docs
that name code in it, each with how many sentences do, so Agent B would have been told that
the usage guide speaks of the command before changing it.

It stays a reading list. Nothing new blocks a gate; a sentence that is still right needs no
answer.

## Cost and risk

The queue of a change pairs each code span that names a function or class, which took it
from 1.9 to 2.4 seconds on this repository in the first build. The packet counts sentences
per doc for a file.

The risk is what is left out on purpose. A sentence that names only a command and says what
the command does is not asked about when that behaviour changes, unless its doc owns the
code, in which case the doc is asked, or it is anchored to a test. That is how it is today,
so nothing gets worse, and this proposal does not fix it.

## Decisions

Answered by the owner on 2026-10-29. On 2026-11-26, after the first build was measured, the
owner changed 1 to 3 and added 4 and 5.

1. **Queue the sentences that name a function or class the change touched**, in
   `list review --changed` alone. First answered as every kind of name, in the queue and in
   `context --after-edit`: that made the queue four times as long, and the loop runs both
   commands, so the same sentences would be read twice.
2. **The packet names the docs that name code in a file, with a count each.** First answered
   as the sentences themselves, capped: for one file that was 544 sentences, and a cap hides
   which docs they are in.
3. **A sentence that names a whole file is not queued for an edit to that file.** First
   answered as any edit: a sentence such as "the backlog is `BACKLOG.md`" stays true however
   that file changes.
4. **A command, an option and an environment variable are not paired with a change.**
5. **An option counts for a file only when the sentence names its command with it, or one
   command alone declares it.** Several commands declare `--confirm`, and a sentence about one
   was counted for another.

## Design detail

- **Today's rule.** `derive-facts-and-leave-meaning-to-the-reader` decides the queue: with a
  change it queues the sentences the change added, reworded or deleted, the claims whose
  evidence it touched, an old owner's sentences about a moved file, and stale summaries;
  without one, sentences naming code, marked by freshness. This [RFC](../GLOSSARY.md#rfc) adds a fifth item to the
  first list. The freshness rule's notion of what a sentence names is reused as it stands
  (`listing/review.py`, `irminsul.binding`, `CodeResolver`, `changed_after`).
- **Touched.** A function or class is touched when the change's diff alters a line in its
  range. The ranges come from the merge base's text for code the change removed or renamed,
  so a sentence naming `Ledger.remove` is queued by the rename that removes it, and from the
  working tree's for the rest. The diff's line ranges come from the same reading `_touches`
  uses for doc lines. Nothing else a span can name is paired with a change: not a command, an
  option, an environment variable or a path.
- **Marker.** A new marker, `names-changed-code`, defined once in the output like the others,
  naming the function or class and the change's file and line.
- **A sentence the change wrote.** It keeps its one `edited` item and carries the marker
  there, as `the-change-queue-asks-about-what-the-change-did-not-write` says; a
  `names-changed-code` item of its own is for a sentence the change did not write.
- **Where.** `list review --changed` and `--base-ref` alone. `context --after-edit` does not
  list these sentences.
- **Packet.** `context <path>` gains `named_by`: each live doc, decision record or guidance
  file with a sentence whose code span names a function, class, command, option or
  environment variable of that path, and the number of such sentences. A decision record is
  read by its `## Decision` alone, as the queue reads it. Plain output lists the eight docs
  with the most sentences and counts the rest; JSON lists every doc. The sentences of one doc
  are what `list review --doc <doc>` lists.
- **Options (decision 5).** In `named_by`, a span that holds an option counts for a file when
  the span or its sentence also names the command that declares it there, or when no other
  command declares an option of that name.
- **What answers for the names not paired.** `code-references/unknown-command`,
  `unknown-option` and `option-not-on-command` are certain findings for a sentence naming a
  command or option the code no longer has. `inventory-drift/undeclared-live-item` and
  `unexplained-live-item` are certain findings for a doc whose `inventory:` list misses a
  command or option the code gained. An anchor may name a test, and then asks about its
  paragraph when that test changes.
- **The loop's wording.** Step 4 of the root `AGENTS.md` and its template
  `src/irminsul/init/scaffolds/AGENTS.md.j2` say "Both also queue the claims whose evidence you
  touched". They gain that the review queue also lists the sentences anywhere that name a
  function or class the change touched. The test that keeps the two equal covers it.
- **Help and the MCP tool.** The help of `list review --changed` and of `context`, and the
  description of the MCP tool `context_for_path`, say what each now lists.
- **Governing records.** The queue's rule is a Decision of
  `derive-facts-and-leave-meaning-to-the-reader`; the packet's contents of
  `agents-get-stateless-read-only-queries-and-one-written-loop`. Both state the rule in place
  with a dated Changes item.
- **Measured** on 2026-11-26 with the first build, which paired every kind of name, by
  `irminsul list review --changed --base-ref <base> --format json` before and after it:

  | Change | Items before | Items after | Carrying the marker |
  |---|---|---|---|
  | `460c44c` | 0 | 0 | 0 |
  | `9759e15` | 26 | 29 | 8 |
  | `dde68e0..ffa39b4` | 48 | 214 | 176 |
  | `ffa39b4..55ab870` | 108 | 179 | 101 |

  Of the 166 items the third change gained, 154 came from three hunks inside the functions
  that declare the commands `check`, `context` and `fix`. Of ten sampled, none was about what
  the change altered. The three that named a function were worth reading. Of 21 sentences the
  implementing change did not write and was asked about, 20 named only a root file such as
  `BACKLOG.md`. The packet for `src/irminsul/cli.py` listed 544 sentences, and its JSON grew
  from 25 to 112 KB.
- **Left open.** A sentence that names a file and something inside it, such as a setting of
  `pyproject.toml`, could be paired with that part alone once
  `claim-evidence-names-a-part` gives the finders. Until then it is not asked about.
- **Not chosen.** Pairing commands and options when they are added, renamed or removed:
  removal and renaming are certain findings already, and an option added to a command named
  in hundreds of sentences would queue them all. A `refs` for code names: the retired
  `refs --symbol` matched `describes` globs and claim evidence, which `context <path>` already
  answers, and a text search is what `grep` does. Making a sentence that names changed code a
  finding: whether it is still right is meaning, which no check knows.
- **Evidence.** The scenario logs are in the lead's dogfood notes of 2026-10-29: agents B
  (`list --json`, `LEDGER_DATE_FORMAT`) and C (`Ledger.remove` to `Ledger.delete`) each found
  the stale docs by grep, and C's `list review --doc` without a change did list the seven
  sentences that `--changed` left out.

## Requirements

### Requirement: A change queues the sentences that name its code
ID: change-queues-sentences-naming-its-code
Provenance: code

With a change, `list review` SHALL queue each sentence the change did not write, in a live
doc, a decision record's Decision or a guidance file, whose code span names a function or
class that the change edited, renamed or deleted, marked `names-changed-code`, and SHALL put
that marker on the `edited` item of a sentence the change wrote that names one. It SHALL NOT
queue a sentence for naming a command, an option, an environment variable or a path that the
change touched.

#### Scenario: A renamed method
- **WHEN** a change renames `Ledger.remove` to `Ledger.delete`, and a component doc names `` `Ledger.remove` `` in a sentence the change does not edit
- **THEN** `list review --changed` queues that sentence, marked `names-changed-code`

#### Scenario: A function whose body changed
- **WHEN** a change edits a line inside `late_fee`, and a guide names `` `late_fee()` `` in a sentence the change does not edit
- **THEN** `list review --changed` queues that sentence, marked `names-changed-code`

#### Scenario: Code the change did not touch
- **WHEN** a change edits only `late_fee`, and a sentence names `` `due_day()` ``
- **THEN** `list review --changed` does not queue that sentence for `names-changed-code`

#### Scenario: A command whose function changed
- **WHEN** a change edits the function that declares the `list` command, and the usage guide names `` `ledger list` `` in a sentence the change does not edit
- **THEN** `list review --changed` does not queue that sentence for `names-changed-code`

#### Scenario: A file that is named and edited
- **WHEN** a change edits `BACKLOG.md`, and a sentence the change does not edit names `` `BACKLOG.md` ``
- **THEN** `list review --changed` does not queue that sentence for `names-changed-code`

### Requirement: The packet names the docs that name code in a file
ID: packet-names-docs-naming-a-file
Provenance: code

`irminsul context <path>` SHALL list, under `named_by`, each live doc, decision record and
guidance file with a sentence whose code span names a function, class, command, option or
environment variable of that path, with the number of such sentences, the eight docs with the
most in the plain output with a count of the rest, and every doc in the JSON. An option SHALL
count only when its sentence names the command that declares it, or one command alone
declares it.

#### Scenario: A guide names a command
- **WHEN** `irminsul context src/ledger/cli.py` runs and the usage guide names `` `ledger list` `` in two sentences
- **THEN** the packet's `named_by` holds the usage guide with a count of 2

#### Scenario: More than eight docs
- **WHEN** eleven docs name code in the path
- **THEN** the plain output lists eight of them and says three more do, and the JSON lists all eleven

#### Scenario: An option two commands declare
- **WHEN** two commands declare `--confirm`, one of them in the path, and a sentence names `` `--confirm` `` with no command
- **THEN** that sentence is not counted for the path

## Tasks

- `T1` Read the change's line ranges for source files and pair the code spans that name a function or class against the merge base and the working tree. (req: change-queues-sentences-naming-its-code)
- `T2` Queue the paired sentences with the `names-changed-code` marker, and mark the `edited` item of a sentence the change wrote. (req: change-queues-sentences-naming-its-code)
- `T3` Add `named_by` to the packet, by doc with a count. (req: packet-names-docs-naming-a-file)
- `T4` Say it in step 4 of the root `AGENTS.md` and its template. (component: init)
- `T5` State the rules in the two governing records with dated Changes items. (component: context)
- `T6` Say what each command lists in the help of `list review` and `context` and in the MCP tool's description. (component: cli)

## Resolution

Accepted by the owner on 2026-10-29, with the answers recorded under Decisions, and resolved by [Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md), whose Changes item records it. [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) records its part too. The owner changed decisions 1 to 3 and added 4 and 5 on 2026-11-26. Each rule joins its record's Decision with the implementation, as an edit in place.
