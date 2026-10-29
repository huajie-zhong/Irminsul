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
  - languages
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
summary: "`new`, `list`, and `fix` commands, and the agent manifest `fix` rewrites."
implements:
  - an-rfc-has-an-owners-part-and-an-agents-part
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

Scaffolds a new doc atom from a Jinja template under `src/irminsul/new/templates/`. Every kind is named by the slug of its title, with no number ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): a slug whose file exists is refused unless `--force` is passed, so two branches that pick one name collide on one path, and a slug another doc already uses as its id is refused outright. `component` takes `--describes` and `--tests` to fill the frontmatter lists and `--from-surface` to derive a `## Surface` section from the claimed paths. A `--describes` value that matches a source file another doc owns today is refused, because the two docs would describe the same code: extend that doc, or pass `--split-from <doc-id>` for each owner. A claimed file that declares none of the commands, options, routes, exports or environment variables `--from-surface` derives is named in one note that says what a surface is, and contributes nothing to the section. The component scaffold holds one guiding comment under its title, as the RFC scaffold's sections do: what a component doc says, and the three ways to tie a sentence to code, a code span, an anchor marker and a claim. It spells neither marker out in full, so no check reads the comment as an anchor or a claim. The RFC scaffold's commented examples follow the [requirement grammar](change.md), so uncommenting one gives a block `requirement-grammar` accepts. It is written in two parts ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)): `weight: large` and the owner's sections Summary, Problem, How it works, Cost and risk and Decisions, or with `--small` `weight: small` and Summary and Decisions only, then `## Design detail`, `## Requirements` and `## Tasks` in both. Each section holds one guiding comment and no text, so a scaffolded RFC is a skeleton to fill in, and `rfc-structure` reports its owner's sections as empty until the author writes under them.

## `irminsul list {undocumented,lifecycle,baseline}`

Thin wrappers over existing checks, for the listings that are more than one check's findings, which `irminsul check --only <check>` prints. Each takes its check's findings through `run_check`, so they carry the classes `check` reports and an ignore comment answers them as it does there. `--format json` emits the same finding records as [`irminsul check --format json`](checks.md), `data` and `fixable`/`fix_command` included: `lifecycle` wraps checks that implement fixes, so a separate serializer would be the one findings surface that hides fixability from agents.

`undocumented --all` drops the covered-directory heuristic of `uniqueness` and lists every source file with no doc claim except the built-in noise files, grouped by directory: the brownfield on-ramp for a repo with little source-ownership mapping. A plain `lifecycle` run lists findings only, and an accepted RFC nobody has implemented raises none until a threshold elapses, so it closes by naming the waiting RFCs and pointing at `--queue`. A draft RFC whose code spans name at least two live identities and nothing absent is `review-shipped` work, evidence that the proposal may already have shipped and never a recommended state, and an RFC without `rfc_state` is `classify` work, because choosing its state is a human decision the queue keeps visible rather than guessing. `list baseline` reads the [baseline](baseline.md) and prints each entry as `hidden` or `fixed`.

## `irminsul list review`

The semantic half of doc–code consistency, as a queue rather than findings. Each item is selected by a fact, never by the words a sentence uses, and its marker names the fact ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)); the command prints what each marker it shows means, so no document restates them. Without `--changed`, every sentence that names code is an item. An item is marked `code_changed_after_doc` when a line of what it names was last changed after the doc's last commit, an uncommitted line and an uncommitted doc counting as changed at the same instant, so a doc edited beside its code is not behind it ([Git helpers](git.md)). Only marked items are listed by default, and so is every item of a doc that git holds no commit of yet, which has no "since" and so reads as `edited`: before its first commit a doc's sentences are all new. An edit elsewhere in the same file does not mark an item, and a behaviour change made through code the sentence does not name is not seen, which is what `--all` is for.
<!-- anchor: src/irminsul/listing/review.py#ReviewItem.code_changed_after_doc @sha256:40f2c7be880b -->

`--changed` and `--base-ref` ask what a change asks a reader to re-read. Every sentence on a changed line whose prose its doc did not already say at the base is an item, whatever it says, because a sentence the reader has not read is the reason to look and a changed line is not: one sentence added to a long paragraph queues that sentence, and a rewrapped paragraph queues none. A deleted sentence is queued, never reported as a finding, because whether the deletion was right is a judgment: the code it described may be gone too. Both sides are read as the queue reads a doc, so a decision record is compared by its `## Decision` alone: a sentence moved into it is `edited`, one moved out of it is `removed-sentence`, and one deleted from its Context is neither. The `governing-claim` entries are the claims [context](context.md) reports for the touched files, so the two surfaces name the same set.

A code name is `unbound-name` only when nothing in the repository resolves it and the enabled languages do not define it themselves: `CodeResolver` holds the union of their [profiles](languages.md)' `builtins`, so `IndexError` in a Python repository is the language's and is not queued, which is why this component depends on `languages`.

Whatever it lists, the command exits 0: it points a reader at what to check and never decides whether a sentence is true.

## `irminsul fix`

Applies deterministic remediations for the findings of the checks in `checks.enabled`, or of the registered checks `--only` names, enabled or not — the same selection as `irminsul check`. A check opts in by exposing a `fixes(findings, graph)` method that returns `Fix` objects, and each fix only ever remediates a finding the check actually emits ([Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)).

A `--dry-run` lists the edits it would apply, per fix, while a live run groups fixes by path and lists the files it actually wrote, because a group whose combined result equals the original is skipped; the dry-run list cannot stand in for what changed. Fixes that modify or remove existing content or load-bearing metadata are tagged `requires_confirm` and are held back, listed but not written, unless `--confirm` is passed; only purely additive inverse pointers apply by default.
<!-- anchor: src/irminsul/checks/base.py#Fix.requires_confirm @sha256:6e42d13129d7 -->

### The agent manifest

The [`docs/AGENTS.md`](../AGENTS.md) manifest is the one generated file, and `agents-manifest` supplies its fixes: a missing manifest is scaffolded, and a generated section that has drifted from the doc graph is rewritten while the curated Foundations and Protocol sections are kept. A manifest that cannot be read as UTF-8, or whose generated-section markers do not parse, gets no fix — rebuilding either from the template would delete every curated section in it, and the finding says which repair is the reader's. The markers parse when one start marker precedes one end marker outside a code fence, so a manifest with a second pair is refused rather than guessed between. The fix writes derived rows only; it never writes prose or infers intent from code.

A check that judges the manifest's prose reads it through `without_generated_region`, which blanks the table and keeps every line number, because the rows repeat summaries that are judged, and can be answered, only in the docs they come from. Markers that do not parse blank nothing.

## Scope & Limitations

`list` subcommands are read-only — they report findings but do not modify any docs. `fix` applies deterministic, pre-coded remediations only, and the manifest table it writes is derived from the doc graph rather than from prose or source code.

## Implemented requirements

- **an-rfc-has-an-owners-part-and-an-agents-part#new-rfcs-are-written-in-two-parts** — `irminsul new rfc` SHALL write the owner's sections Summary, Problem, How it works, Cost and risk and Decisions, in that order, above `## Design detail`, followed by `## Requirements` and `## Tasks`. (provenance: code; [RFC](../rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md))
  <!-- anchor: src/irminsul/cli.py#new_rfc @sha256:aced4229a0cc -->
  <!-- anchor: tests/test_cli_new.py#test_a_new_rfc_is_written_in_two_parts @sha256:7fea3564fc4f -->
  <!-- anchor: tests/test_cli_new.py#test_a_new_small_rfc_is_written_in_two_parts @sha256:8ff92cc63c01 -->
