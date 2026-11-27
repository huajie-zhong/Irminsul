---
id: new-list-regen
title: New / List / Fix commands
status: stable
describes:
  - src/irminsul/new/**
  - src/irminsul/listing/**
  - src/irminsul/regen/**
  - src/irminsul/fix.py
  - src/irminsul/code_references.py
  - src/irminsul/ownership_moves.py
depends_on:
  - checks
  - config
  - context
  - docgraph
  - file-writing
  - frontmatter
  - git
  - languages
  - surface
  - user-errors
owns_tests:
  - tests/test_cli_fix.py
  - tests/test_cli_list.py
  - tests/test_cli_new.py
  - tests/test_fix_agents_manifest.py
  - tests/test_fix_glossary.py
  - tests/test_fix_inventory_drift.py
  - tests/test_fix_policy.py
  - tests/test_fix_rfc_follow_through.py
  - tests/test_fix_rfc_required_updates.py
  - tests/test_list_review.py
  - tests/test_review_changed_code.py
summary: "`new`, `list`, and `fix` commands, and the agent manifest `fix` rewrites."
implements:
  - an-rfc-has-an-owners-part-and-an-agents-part
  - a-change-re-asks-the-sentences-that-name-its-code
  - the-change-queue-asks-about-what-the-change-did-not-write
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - check
      - fix
      - list review
---

# New / List / Fix commands

## `irminsul new {adr,component,rfc}`

Scaffolds a new doc atom from a Jinja template under `src/irminsul/new/templates/`. Every kind is named by the slug of its title, with no number ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): a slug whose file exists is refused unless `--force` is passed, so two branches that pick one name collide on one path, and a slug another doc already uses as its id is refused outright. `component` takes `--describes` and `--tests` to fill the frontmatter lists and `--from-surface` to derive a `## Surface` section from the claimed paths. A `--describes` value that matches a source file another doc owns today is refused, because the two docs would describe the same code: extend that doc, or pass `--split-from <doc-id>` for each owner. A claimed file that declares none of the commands, options, routes, exports or environment variables `--from-surface` derives is named in one note that says what a surface is, and contributes nothing to the section. The component scaffold holds one guiding comment under its title, as the RFC scaffold's sections do: what a component doc says, the three ways to tie a sentence to code, a code span, an anchor marker and a claim, and as a fourth line the advice to anchor a sentence that says what the code does to the test that asserts it, with the `irminsul anchors --suggest --doc <doc>` that lists those tests ([Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)). It spells neither marker out in full, so no check reads the comment as an anchor or a claim. The RFC scaffold's commented examples follow the [requirement grammar](change.md), so uncommenting one gives a block `requirement-grammar` accepts. It is written in two parts ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): `weight: large` and the owner's sections Summary, Problem, How it works, Cost and risk and Decisions, or with `--small` `weight: small` and Summary and Decisions only, then `## Design detail`, `## Requirements` and `## Tasks` in both. Each section holds one guiding comment and no text, so a scaffolded RFC is a skeleton to fill in, and `rfc-structure` reports its owner's sections as empty until the author writes under them.

Nor is the code span that comment shows as an example a name the doc uses: the review queue reads no sentence on a line an HTML comment opens at its start, nor on the lines after it up to and including the one that closes it, and `anchors --suggest` lists no span inside one. A comment opened after prose on a line is read with that line. A comment marker quoted in a code span is prose and opens nothing.
<!-- anchor: tests/test_list_review.py#test_a_comment_over_several_lines_holds_no_sentence @sha256:fbc3efaeba09 -->
<!-- anchor: tests/test_binding.py#test_suggest_reads_no_name_in_the_component_scaffolds_comment @sha256:087bb132e3b4 -->

## `irminsul list {undocumented,lifecycle,baseline}`

Thin wrappers over existing checks, for the listings that are more than one check's findings, which `irminsul check --only <check>` prints. Each takes its check's findings through `run_check`, so they carry the classes `check` reports and an ignore comment answers them as it does there. `--format json` emits the same finding records as [`irminsul check --format json`](checks.md), `data` and `fixable`/`fix_command` included: `lifecycle` wraps checks that implement fixes, so a separate serializer would be the one findings surface that hides fixability from agents.

`undocumented --all` drops the covered-directory heuristic of `uniqueness` and lists every source file with no doc claim except the built-in noise files, grouped by directory: the brownfield on-ramp for a repo with little source-ownership mapping. A plain `lifecycle` run lists findings only, and an accepted RFC nobody has implemented raises none until a threshold elapses, so it closes by naming the waiting RFCs and pointing at `--queue`. A draft RFC whose code spans name at least two live identities and nothing absent is `review-shipped` work, evidence that the proposal may already have shipped and never a recommended state, and an RFC without `rfc_state` is `classify` work, because choosing its state is a human decision the queue keeps visible rather than guessing. `list baseline` reads the [baseline](baseline.md) and prints each entry as `hidden` or `fixed`.

## `irminsul list review`

The semantic half of doc–code consistency, as a queue rather than findings. Each item is selected by a fact, never by the words a sentence uses, and its marker names the fact ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)); the command prints what each marker it shows means, so no document restates them. Without a change, every sentence that names code is an item. An item is marked `code_changed_after_doc` when a line of what it names was last changed after the doc's last commit, an uncommitted line and an uncommitted doc counting as changed at the same instant, so a doc edited beside its code is not behind it ([Git helpers](git.md)). Only marked items are listed by default, and so is every item of a doc that git holds no commit of yet, which has no "since" and so reads as `edited`: before its first commit a doc's sentences are all new. An edit elsewhere in the same file does not mark an item, and a behaviour change made through code the sentence does not name is not seen, which is what `--all` is for.
<!-- anchor: src/irminsul/listing/review.py#ReviewItem.code_changed_after_doc @sha256:40f2c7be880b -->

A change has two lists, and a run prints one ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)). `--changed`, which `--base-ref` alone also means, is what the change asks its author to re-read: the sentences it left as they were and may have made stale. `--written` is what the change wrote, for whoever reviews it. Both name the change alike, the uncommitted work against `HEAD` alone or the range from the merge base with `--base-ref`, and `--committed-only` ends it at `HEAD` for both; given together they exit 2. The JSON of either carries `list`, `changed` or `written`, which a queue without a change does not. `build_review` finds the written sentences for both, so that `--changed` does not ask again about a sentence the change wrote.

In `--written`, every sentence on a changed line whose prose its doc did not already say at the base is an item, whatever it says, because a sentence the reader has not read is the reason to look and a changed line is not: one sentence added to a long paragraph queues that sentence, and a rewrapped paragraph queues none. A deleted sentence is queued, never reported as a finding, because whether the deletion was right is a judgment: the code it described may be gone too. A sentence changed in place is one `edited` item that shows the sentence it replaced as `was`, not an edit and a deletion: the old and new sentences pair in order within the run the change replaced, and a sentence that only moved is queued by neither. In a Markdown file an ordered list item that only took a new number is queued by neither as well, when the change left the file with more or fewer ordered items: its words are the base's, and the number says where it sits. A number that changed while the file kept as many ordered items stays an edit, because the number may be what the line says. Both sides are read as the queue reads a doc, so a decision record is compared by its `## Decision` alone: a sentence moved into it is `edited`, one moved out of it is `removed-sentence`, and one deleted from its Context is neither. That is all `--written` lists.

`--changed` lists the rest: a claim whose evidence the change touched, as `governing-claim`; the `summary:` a body edit left as it was, as `stale-summary`; a sentence a file's previous owner keeps about a file the change moved, as `moved-file`; and the sentences that name changed code, below. The `governing-claim` entries are the claims [context](context.md) reports for the touched files, so the two surfaces name the same set. Each item but one kind is about a sentence the change left as it was, though what selects it may be the change's own edit to that doc: an edit to a body selects the untouched summary, and an edit to `describes:` the previous owner's sentences. So a sentence a previous owner keeps about a moved file, reworded in the same change, is `moved-file` in one list and `edited` in the other.

A change also queues each sentence, in any file the queue reads, whose code span names a function or class the change touched, marked `names-changed-code`, so a guide or a README that owns no code is asked about a function when the function changes. `ChangePairing` pairs each span as the queue does without a change, through `CodeResolver`, on both sides of the change, and keeps only a span that names a function or class: a command, an option, an environment variable, any other surface identity and a path are paired with no change, because too many sentences name them for too many reasons ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)). `CodeResolver` reads a file's functions and classes through the [reader](languages.md#readers) its language's profile names, so a name of code in a language no reader reads pairs with nothing, and where an enabled language writes its paths with `::`, as Rust does, a span written that way is read as the dotted path. A span that names a function the code also declares as a surface identity, such as an MCP tool, names that identity and is not paired. An export is the exception, since its identity is the name of a definition and nothing more: a span naming one names the one definition of that name in the export's language, wherever a file re-exports it, with its lines. A definition's lines are its decorator or attribute lines, the line that names it and its body, as an [anchor](anchors.md) reads one, which `CodeResolver.definitions` gives. It is touched when the lines it has where the change ends, the working tree, or `HEAD` under `--committed-only`, are not the lines it had at the base. So an added or altered line counts where the change puts it and a deleted one where it lay, and deleting the function below one does not touch it, though git's diff files a deletion under the line before it, which may be the last line of the definition above. A definition moved in its file with its lines unchanged is not touched. `SourceAtCommit` reads the merge base through the [git helpers](git.md), a file the change left alone from the working tree's snapshot and the rest from the commit, and the [surface](surface.md) extractors run over it as they do over the working tree, so a span that named a command there is not read as a function, which is why this component depends on `git` and `surface`. The definition a span named there is followed into the file as the change leaves it, under the path a rename git reports gave it, and it is told from another of the same name by its class. So a function is still asked about once a second definition has taken its name and the span pairs with neither, and a method renamed beside a method of that name in another class is still removed. When the file no longer defines it, the change removed or renamed it, unless the file no longer parses: what it defines cannot be read then, and each definition a sentence named is listed as changed, with no line. A file a rename took to a name no reader reads defines nothing a sentence can name, so its definitions are listed as removed, unless it no longer parses as the language it was read as before. Each item lists what was touched as `changed_code`: the span, the bare name, the file, and the first line of the definition that differs, or for a removed one the line that defined it at the base. A sentence the change itself wrote is not queued in `--changed`: its one `edited` item in `--written` takes the marker, so every `names-changed-code` item of `--changed` is about a sentence the change left as it was. Code spans alone are paired, not the identities plain prose names, and `context --after-edit` lists none of these sentences. The pairing is as loose as it is without a change: a bare name pairs with the one function or class of that name wherever it is defined and with nothing when it has two definitions, in two files or in one, such as a property and its setter, though a test that shares its name with one other definition, as a Rust unit test may share its function's, leaves the name to that one; a class is touched by a change to any line of its methods, and a function by one to a function nested in it.
<!-- anchor: src/irminsul/listing/review.py#ReviewItem.changed_code @sha256:22030bae5ecf -->
<!-- anchor: src/irminsul/listing/review.py#_sentences_naming_changed_code @sha256:0c4129753f51 -->
<!-- anchor: tests/test_review_changed_code.py#test_a_file_renamed_to_a_name_no_reader_reads_removed_its_functions @sha256:e1af4868a184 -->

Either list says what it compared with, in the header and as `base` in the JSON: `HEAD` when no `--base-ref` is given, which cannot see commits the branch already holds, else the merge base of that ref and `HEAD`. Without a base, when `unread_commits_note` finds `origin/HEAD`'s target, `origin/main` or `origin/master` lacking commits that `HEAD` holds, a `note` names that ref and the `--base-ref` that covers them.

A code name in a sentence of `--written` is `unbound-name` only when nothing in the repository resolves it and the enabled languages do not define it themselves: `CodeResolver` holds the union of their [profiles](languages.md)' `builtins`, so `IndexError` in a Python repository is the language's and is not queued, which is why this component depends on `languages`.

Whatever it lists, the command exits 0: it points a reader at what to check and never decides whether a sentence is true.

## `irminsul fix`

Applies deterministic remediations for the findings of the checks in `checks.enabled`, or of the registered checks `--only` names, enabled or not — the same selection as `irminsul check`. A check opts in by exposing a `fixes(findings, graph)` method that returns `Fix` objects, and each fix only ever remediates a finding the check actually emits ([Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)).

A `--dry-run` lists the edits it would apply, per fix, while a live run groups fixes by path and lists the files it actually wrote, because a group whose combined result equals the original is skipped; the dry-run list cannot stand in for what changed. Fixes that modify or remove existing content or load-bearing metadata are tagged `requires_confirm` and are held back, not written, unless `--confirm` is passed; only purely additive inverse pointers apply by default. A plain run says how many fixes it held and that `--dry-run --confirm` lists them.
<!-- anchor: src/irminsul/checks/base.py#Fix.requires_confirm @sha256:6e42d13129d7 -->

### The agent manifest

The [`docs/AGENTS.md`](../AGENTS.md) manifest is the one generated file, and `agents-manifest` supplies its fixes: a missing manifest is scaffolded, and a generated section that has drifted from the doc graph is rewritten while the curated Foundations and Protocol sections are kept. A manifest that cannot be read as UTF-8, or whose generated-section markers do not parse, gets no fix — rebuilding either from the template would delete every curated section in it, and the finding says which repair is the reader's. The markers parse when one start marker precedes one end marker outside a code fence, so a manifest with a second pair is refused rather than guessed between. The fix writes derived rows only; it never writes prose or infers intent from code.

A check that judges the manifest's prose reads it through `without_generated_region`, which blanks the table and keeps every line number, because the rows repeat summaries that are judged, and can be answered, only in the docs they come from. Markers that do not parse blank nothing.

## Scope & Limitations

`list` subcommands are read-only — they report findings but do not modify any docs. `fix` applies deterministic, pre-coded remediations only, and the manifest table it writes is derived from the doc graph rather than from prose or source code.

`list review --written` pairs an edited sentence with the one it replaced by position, not by similarity: within a run the change rewrote, the first new sentence pairs with the first old sentence the file no longer has. An insertion before a rewrite can therefore pair a new sentence with an old one it did not replace, so its `was` names that one. This is accepted, because a threshold would guess where order does not, and the queue shows both texts, so the reader sees the mismatch. A sentence both moved and reworded in one edit has no run to pair in, so it is queued as `edited` and as `removed-sentence`. Whether a list item was only renumbered is judged for the whole file, not for its list: once the file has gained or lost an ordered item, every item whose words the base has under another number is set aside, so a number that is itself the content, changed in the same edit, is not queued.

## Implemented requirements

- **an-rfc-has-an-owners-part-and-an-agents-part#new-rfcs-are-written-in-two-parts** — `irminsul new rfc` SHALL write the owner's sections Summary, Problem, How it works, Cost and risk and Decisions, in that order, above `## Design detail`, followed by `## Requirements` and `## Tasks`. (provenance: code; [RFC](../rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md))
  <!-- anchor: src/irminsul/cli.py#new_rfc @sha256:aced4229a0cc -->
  <!-- anchor: tests/test_cli_new.py#test_a_new_rfc_is_written_in_two_parts @sha256:7fea3564fc4f -->
  <!-- anchor: tests/test_cli_new.py#test_a_new_small_rfc_is_written_in_two_parts @sha256:8ff92cc63c01 -->
- **a-change-re-asks-the-sentences-that-name-its-code#change-queues-sentences-naming-its-code** — With a change, `list review` SHALL queue each sentence the change did not write, in a live doc, a decision record's Decision or a guidance file, whose code span names a function or class that the change edited, renamed or deleted, marked `names-changed-code`, and SHALL put that marker on the `edited` item of a sentence the change wrote that names one. A function or class is edited when its lines, its decorators included, differ between the merge base and where the change ends. It SHALL NOT queue a sentence for naming a command, an option, an environment variable or a path that the change touched. Functions and classes are those of the source files a language's reader reads: the RFC paired Python's alone, and [Each language reads its code through one interface](../rfcs/each-language-reads-its-code-through-one-interface.md) widened it. (provenance: code; [RFC](../rfcs/a-change-re-asks-the-sentences-that-name-its-code.md))
  <!-- anchor: src/irminsul/listing/review.py#_sentences_naming_changed_code @sha256:0c4129753f51 -->
  <!-- anchor: src/irminsul/listing/changed_code.py#ChangePairing.touched @sha256:d52e6b1c4925 -->
  <!-- anchor: tests/test_review_changed_code.py#test_renaming_a_method_queues_the_sentence_that_names_the_old_name @sha256:1518bcce2c55 -->
  <!-- anchor: tests/test_review_changed_code.py#test_a_function_whose_body_changed_queues_the_guide_that_names_it @sha256:d907b712f141 -->
  <!-- anchor: tests/test_review_changed_code.py#test_a_sentence_naming_a_function_the_change_left_alone_is_not_queued @sha256:bf6fe45d167c -->
  <!-- anchor: tests/test_review_changed_code.py#test_deleting_the_function_below_one_does_not_touch_the_one_above @sha256:40021132186f -->
  <!-- anchor: tests/test_review_changed_code.py#test_a_command_whose_function_changed_queues_no_sentence_that_names_it @sha256:d239d1d4297f -->
  <!-- anchor: tests/test_review_changed_code.py#test_a_file_that_is_named_and_edited_queues_no_sentence_that_names_it @sha256:9e98fda5ed20 -->
  <!-- anchor: tests/test_languages_typescript_reader.py#test_an_edit_to_a_function_queues_the_guide_that_names_it @sha256:4b306ec38aad -->
  <!-- anchor: tests/test_languages_go_reader.py#test_editing_late_fee_queues_the_guide_sentence_that_names_it @sha256:fb87b87862c3 -->
  <!-- anchor: tests/test_languages_rust_reader.py#test_an_edit_to_a_rust_function_queues_the_guide_that_names_it @sha256:8dee1f2e01b6 -->
- **the-change-queue-asks-about-what-the-change-did-not-write#change-queue-holds-no-written-sentence** — `list review --changed` SHALL queue no `edited` item and no `removed-sentence` item, and SHALL queue every other item as it does without this change. (provenance: code; [RFC](../rfcs/the-change-queue-asks-about-what-the-change-did-not-write.md))
  <!-- anchor: src/irminsul/listing/review.py#build_review @sha256:b68ad280167f -->
  <!-- anchor: tests/test_list_review.py#test_a_reworded_sentence_queues_its_docs_summary_and_no_edit @sha256:918a135bffac -->
  <!-- anchor: tests/test_list_review.py#test_a_governing_claim_is_queued_when_only_its_code_changed @sha256:3e2c48d3081e -->
- **the-change-queue-asks-about-what-the-change-did-not-write#written-sentences-are-their-own-list** — `list review --written` SHALL queue the `edited` and `removed-sentence` items of the change, each as `list review --changed` built it before this change, and SHALL queue nothing else. (provenance: code; [RFC](../rfcs/the-change-queue-asks-about-what-the-change-did-not-write.md))
  <!-- anchor: src/irminsul/listing/review.py#build_review @sha256:b68ad280167f -->
  <!-- anchor: tests/test_list_review.py#test_a_reworded_sentence_under_the_flag_is_one_edit_beside_the_one_it_replaced @sha256:0d1c52069390 -->
  <!-- anchor: tests/test_list_review.py#test_a_deleted_sentence_under_the_flag_is_a_removed_sentence @sha256:034e2c315117 -->
