---
id: new-list-regen
title: New / List / Regen / Fix commands
status: stable
depends_on:
  - checks
  - config
  - context
  - docgraph
  - frontmatter
describes:
  - src/irminsul/new/**
  - src/irminsul/listing/**
  - src/irminsul/regen/**
  - src/irminsul/fix.py
  - src/irminsul/code_references.py
  - src/irminsul/ownership_moves.py
owns_tests:
  - tests/test_cli_fix.py
  - tests/test_cli_list.py
  - tests/test_cli_new.py
  - tests/test_cli_regen.py
  - tests/test_fix_glossary.py
  - tests/test_fix_inventory_drift.py
  - tests/test_fix_policy.py
  - tests/test_fix_rfc_follow_through.py
  - tests/test_fix_rfc_required_updates.py
  - tests/test_list_review.py
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - check
      - fix
      - list review
---

# New / List / Regen / Fix commands

Doc-author UX commands for creating, finding, regenerating, and remediating documentation atoms.

## `irminsul new {adr,component,rfc}`

Scaffolds a new doc atom from a Jinja template under `src/irminsul/new/templates/`. Every kind is named by the slug of its title, with no number ([Records are named by slug](../decisions/records-are-named-by-slug.md)): ADRs go to `docs/decisions/<slug>.md`, components to `docs/components/<slug>.md`, and RFCs to `docs/rfcs/<slug>.md`. The slug keeps ASCII letters, digits, and hyphens, at most 64 characters, so a link to the file needs no percent-encoding; a title with none of them is a usage error. A slug whose file exists is refused unless `--force` is passed, so two branches that pick one name collide on one path, and a slug another doc already uses as its id is refused outright. Every generated doc has valid frontmatter that immediately passes `FrontmatterCheck`, and is linked from the INDEX in its folder when one exists.

The ADR scaffold emits one `## Status`, `## Context`, `## Decision`, `## Alternatives Considered`, and `## Consequences` section, with Status initialized to `Proposed.`. It leaves lifecycle relationship fields absent until a real relationship exists; RFC state is governed by structured lifecycle metadata rather than inferred from the ADR body.

The `component` kind accepts repeatable `--describes` and `--tests` options that populate the scaffolded frontmatter lists instead of leaving them empty, so a new component doc can claim its sources in one command. Values are stored repo-relative in POSIX form; a value that does not exist on disk prints a yellow warning but is still written, since the file may be about to be created. With `--from-surface`, the scaffolded body gains a `## Surface` section derived from the claimed paths at scaffold time (CLI commands, HTTP endpoints, env vars, TS exports — whichever extractors find anything); paths with nothing derivable get a note and no section. A `--describes` value that matches a source file another doc owns today is refused, because the two docs would describe the same code; extend that doc instead, or pass `--split-from <doc-id>` for each owner, which writes a `Split from` link to it into the new doc and prints which files to remove from its claim and prose.

## `irminsul list {orphans,stale,undocumented,lifecycle,baseline}`

Thin wrappers over existing checks: `orphans` delegates to `OrphansCheck`, `stale` to `StaleReaperCheck`, `undocumented` to `UniquenessCheck` (filtering to omission warnings), and `lifecycle` combines `RfcLifecycleCheck` with the required-update, stale-claim, and draft-link findings of `RfcFollowThroughCheck`. Output is plain text by default; for `orphans`, `stale`, `undocumented`, and plain `lifecycle`, `--format json` emits a JSON array of the same finding records [`irminsul check --format json`](checks.md) produces — including `data` and `fixable`/`fix_command`. That sharing is deliberate: `lifecycle` wraps checks that *do* implement fixes, so a separate serializer here would be the one findings surface that hides fixability from agents. `lifecycle --queue`, `undocumented --all`, and `review` emit their own shapes, described below.

By default `undocumented` only reports files in covered directories — a directory that holds claimed code, or one added inside a directory that does, so a new subdirectory of documented code does not escape by being new. The `--all` flag drops that heuristic and lists every source file with no doc claim except the built-in noise files such as `__init__.py`, grouped by directory with per-directory counts, directories sorted by undocumented count descending; this is the brownfield on-ramp for repos with little or no existing source-ownership mapping. In JSON mode each `--all` entry carries the file `path` and its parent `dir`.

`list lifecycle --queue` also includes accepted implementation backlog entries,
premature implementation evidence, and stable
live docs that still point at draft RFCs. Each category receives a deterministic
priority, action kind, and suggested next command. Without `--queue` the listing is
findings only, and an accepted RFC nobody has implemented raises none until a threshold
elapses — so a plain run named no work over a backlog years deep. It now closes by naming
the accepted RFCs that are waiting and pointing at `--queue`.

A draft RFC whose code spans name at least two live identities — options, commands, or configured surface kinds — and nothing absent appears as `review-shipped` work, listing those identities. It is evidence that the proposal may already have shipped, never a recommended state; flags declared under a `cli-options` entry's `foreign` list are ignored.

An RFC without `rfc_state` appears as `classify` work: choosing its state is a human decision, so the queue keeps it visible rather than guessing.

`list baseline` reads the [baseline](baseline.md) file and runs the enabled checks without it, then prints each entry as `hidden`, when it still matches a finding, or `fixed`, when it matches nothing and `check --update-baseline` would remove it. `--format json` emits `{"path": ..., "entries": [...]}` with each entry's `state`, `check`, `path`, and `message`.

## `irminsul list review`

The semantic half of doc–code consistency, as a queue rather than findings. Each item is a sentence that states current truth — any prose in a stable live doc or a guidance file named by `paths.extra_docs`, the `## Decision` section of a decision record, or a glossary definition — and makes a checkable assertion: an exit code, an output format, a default, an absolute such as "always" or "there is no", a count of commands or checks, a promise of later work, an enforcement verb such as "catches", "rejects", or "fails", a scope word such as "every", "each", or "only", or an enumeration of three or more identities of one surface kind. Every code span in it is resolved to the defining location: options and commands through the surface extractors, configured surface kinds by exact or dotted name, Python functions and classes by name, and any repository file by path. An identity that cannot be an ordinary word, such as a hyphenated check name or `--strict`, is resolved in plain prose too. An item is marked `code_changed_after_doc` when a line of what it names was last changed after the doc's last commit: the full line range of a function or class, the declaring line of a surface identity, or the whole file for a path, read from one `git blame` per referenced file, with uncommitted lines counting as changed. Only marked items are listed by default; `--all` lists every item, marked ones first. An edit elsewhere in the same file does not mark an item, and a behaviour change made through code the sentence does not name is not seen, which is what `--all` is for. `--changed` keeps only sentences on lines changed in the working tree compared with `HEAD`, and `--base <ref>` those changed since a git ref; on a changed line a scope or enforcement word counts even when the sentence names no code, because the edit is the reason to look, and every such sentence is listed. Table rows are reviewed as one sentence each. On a changed line, a code name that no surface, symbol, or path resolves and no anchor in the doc binds is listed under `unbound`, with an `unbound-name` marker, so the writer binds it with an [anchor](anchors.md). When a changed doc's body lines changed but its `summary` line did not, the summary is listed with a `stale-summary` marker, because the manifest, `orient`, and the MCP server show it to every agent. When the change moved a source file from one doc's `describes` to another's, the old owner's sentences that name the file, by path or file name, are listed with a `moved-file` marker. An assertion sentence the change deleted is listed with a `removed-sentence` marker, read from the doc's content at the base ref: every other item is built from a line that still exists, so deleting a sentence used to remove it from the queue as well as from the doc. Whether the deletion was right is a judgment — the code it described may be gone too — so it is queued and never reported as a finding. A claim whose `evidence` names a file the change touched is listed with a `governing-claim` marker — the queue asks [context](context.md) which claims those are, so the two surfaces answer with the same set and one `evidence:<path>` marker per touched file, at the line declaring the claim's id. It is the one entry reached from changed *code* rather than a changed doc line, so a contract stays reviewable through a change that never opened the document stating it; `follows-evidence` claims are left out, because there the code wins outright and changing it settles the question instead of raising one. `--doc <path>` narrows the queue to one doc, and `--format json` emits `{"version": 1, "total": ..., "shown": ..., "items": [...]}`. The command always exits 0: it points a reader at what to check, and never decides whether the sentence is true.

## `irminsul fix`

Applies deterministic remediations for fixable findings selected by `--profile`. The default profile is `enabled`; `enabled` and `all-available` use the same selection policy as `irminsul check`. A check opts in by exposing a `fixes(findings, graph)` method that returns `Fix` objects; each fix only ever remediates a finding the check actually emits ([Deterministic enforcement](../decisions/deterministic-enforcement.md)). The covered checks are `supersession` (deprecation metadata), `rfc-follow-through` (the inverse `implements:` back-link, a resolved RFC's `status`, and its scaffolding section), `inventory-drift` (pruning a drifted item), `glossary-discipline` (linking the first use of a term), and `parent-child` (linking an unlisted sibling from its INDEX, with `--confirm`).

`--dry-run` prints the edits that would be applied without writing files; normal runs group fixes by path and write each file atomically through a temporary file plus rename. Because fixes are grouped, and a group whose combined result equals the original file is skipped, the two runs report different things: a dry run lists the edits it would apply, and a live run lists the files it actually wrote. The dry-run list is per-fix, not per-file, so it cannot stand in for what changed — several fixes may target one doc, and any of them may turn out to be a no-op.

`--format json` emits a versioned record of the run so an agent can consume the outcome without parsing prose, including when nothing was harvested — that is a success with empty collections, not an error. The exact envelope is not restated here; run `irminsul fix --dry-run --format json` to read it. Fixes that modify or remove existing content or load-bearing metadata are tagged `requires_confirm` and are held back — listed but not written — unless `--confirm` is passed; only purely additive inverse pointers apply by default, and so does `supersession`'s `superseded_by` pointer. `--check <name>` harvests fixes from a single active check for targeted runs. Edits go through the shared [frontmatter-edit](frontmatter.md) helpers so every rewrite re-emits keys in canonical order and is idempotent.

## `irminsul regen`

`regen` produces deterministic generated artifacts and nothing else — it never writes prose or infers intent from code. The single artifact is `agents-md`: it rewrites the generated section of the [`docs/AGENTS.md`](../AGENTS.md) manifest from the doc graph while preserving the curated Foundations and Protocol sections.

The exact, current subcommand list is derived from the Typer app, not restated here — run `irminsul surface cli`.

## Scope & Limitations

`list` subcommands are read-only — they report findings but do not modify any docs. `regen` generates deterministic artifacts only; it does not produce prose descriptions or infer intent from source code. `fix` applies deterministic, pre-coded remediations only.
