---
id: checks
title: Checks
status: stable
describes:
  - src/irminsul/checks/**
depends_on:
  - adoption-record
  - anchors
  - change
  - config
  - docgraph
  - frontmatter
  - git
  - init
  - languages
  - new-list-regen
  - surface
  - user-errors
owns_tests:
  - tests/test_check_flags.py
  - tests/test_check_runner.py
  - tests/test_checks_adr_structure.py
  - tests/test_checks_agents_manifest.py
  - tests/test_checks_anchors.py
  - tests/test_checks_boundary.py
  - tests/test_checks_change_binding.py
  - tests/test_checks_claim_anchor.py
  - tests/test_checks_claim_provenance.py
  - tests/test_checks_code_references.py
  - tests/test_checks_coverage.py
  - tests/test_checks_dependency.py
  - tests/test_checks_doc_refs.py
  - tests/test_checks_doc_structure.py
  - tests/test_checks_external_links.py
  - tests/test_checks_foundation_readiness.py
  - tests/test_checks_frontmatter.py
  - tests/test_checks_globs.py
  - tests/test_checks_glossary.py
  - tests/test_checks_history_depth.py
  - tests/test_checks_links.py
  - tests/test_checks_mtime_drift.py
  - tests/test_checks_new_dependency.py
  - tests/test_checks_orphans.py
  - tests/test_checks_parent_child.py
  - tests/test_checks_phantom_layer.py
  - tests/test_checks_pipeline_classes.py
  - tests/test_checks_prose_file_reference.py
  - tests/test_checks_requirement_grammar.py
  - tests/test_checks_retired_references.py
  - tests/test_checks_rfc_follow_through.py
  - tests/test_checks_rfc_lifecycle.py
  - tests/test_checks_rfc_required_updates.py
  - tests/test_checks_rfc_structure.py
  - tests/test_checks_schema_leak.py
  - tests/test_checks_sections.py
  - tests/test_checks_stale_reaper.py
  - tests/test_checks_supersession.py
  - tests/test_checks_uniqueness.py
  - tests/test_diff_base_semantics.py
  - tests/test_diff_integrity.py
  - tests/test_diff_integrity_bypasses.py
  - tests/test_diff_worktree.py
  - tests/test_draft_status.py
  - tests/test_finding_codes.py
  - tests/test_finding_enforcement_class.py
  - tests/test_ignore_comments.py
  - tests/test_owned_tests.py
  - tests/test_walk_source_files.py
summary: Registered checks; exact names live in `src/irminsul/checks/__init__.py`.
implements:
  - acknowledge-a-reviewed-co-change-or-evidence-drift
  - a-gate-file-is-sealed-not-scored
  - an-rfc-has-an-owners-part-and-an-agents-part
inventory:
  - kind: checks
    source: src/irminsul/checks/*.py
    explained_in: any
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - check
      - context
      - fix
      - seed
---

# Checks

Checks consume a [DocGraph](docgraph.md) and return `Finding` records with severity, message, and a path/line where applicable. The exact registry surface is defined by the registry in `src/irminsul/checks/__init__.py`.

**What a finding code means, and how to fix it, is `irminsul explain <code>`; `irminsul explain <check>` lists one check's codes.** Every code carries its explanation beside the code that raises it, and each check's module docstring says why the check is shaped as it is, so this doc restates neither: a second copy would be a cache of a derivable fact, and would go stale exactly where being wrong costs most. What follows is what no single module can say: how the set fits together, and where a check deliberately stops short.

The checks, grouped by what they govern:

- **The graph and its edges** — `frontmatter`, `doc-refs`, `links`, `orphans`, `supersession`, `phantom-layer`, `parent-child`, `uniqueness`, `globs`, `coverage`, `test-ownership`
- **Layer discipline** — `boundary`, `schema-leak`, `foundation-readiness`, `glossary-discipline`, `duplicate-block`, `prose-file-reference`
- **Prose against code** — `claim-provenance`, `claim-anchor`, `code-references`, `inventory-drift`, `import-deps`
- **Records and lifecycle** — `rfc-lifecycle`, `rfc-follow-through`, `requirement-grammar`, `change-binding`, `adr-structure`, `rfc-structure`, `retired-references`, `agents-manifest`
- **Elapsed time and the outside world** — `mtime-drift`, `stale-reaper`, `external-links`

Whether a finding blocks follows its class, which each check declares for every code it explains ([Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)); a test runs every check over the fixture corpus and fails if one emits a severity its class does not allow.

How a correct doc turns a finding green is the code's answer, which a check declares in `answers` beside `classes`: `fix`, the doc or config is wrong; `line`, a reasoned ignore comment on the finding's line; `pin`, a re-pin after re-reading; or `trailer`, an `Irminsul-Reviewed` commit trailer that signs off one change. Every hint and time code declares one, and a certain code only when a trailer answers it, so `answer_of` reads a code with none as the fix its explanation gives. `irminsul explain` prints the answer, and the JSON of a finding carries it as `answer`. A test fails on a hint or time code with no answer.
<!-- anchor: src/irminsul/checks/pipeline.py#answer_of @sha256:2215b944043e -->

A fact about a check that other code acts on is a `CheckFlag` the check declares in `flags`, and `flagged` derives the set from the registry: off unless a project lists it (`opt_in`), answers from commit history (`reads_history`), takes exceptions from the adoption record (`consults_adoption_record`), reaches the network (`uses_network`). No list of check names is kept beside the code that reads one, so renaming a check or adding a sibling cannot leave one stale, and a test reads the source for any module that keeps such a list.
<!-- anchor: src/irminsul/checks/base.py#CheckFlag.opt_in @sha256:905c9f146ced -->
<!-- anchor: src/irminsul/checks/base.py#CheckFlag.reads_history @sha256:7d834b6d32e4 -->
<!-- anchor: src/irminsul/checks/base.py#CheckFlag.consults_adoption_record @sha256:539eb59b4d35 -->
<!-- anchor: src/irminsul/checks/base.py#CheckFlag.uses_network @sha256:3f8f4fc65bb0 -->

`supersession` reads the one direction a successor declares, `supersedes`; the inverse is derived, never written. A superseded doc is `deprecated` or `removed`, because `stale-reaper` asks an aged deprecated doc to become `removed`; `irminsul fix` deprecates only one that is still live. RFC records are excluded: a new proposal must not demand a metadata write to an implemented predecessor, which does not change.

`retired-references` reads fenced examples too, because an obsolete command there is operationally dangerous, so a migration note showing the retired invocation has no in-fence remedy: a Markdown link cannot live inside a fence. Two answers exist and both are deliberate: wrap the example in an HTML comment, which is not read as a current claim, or keep it in the changelog, which is a migration record rather than guidance and so lies outside the audit. A `draft` doc is not such a place: a retired command is as wrong there as in a stable doc.

`adr-structure` and `rfc-structure` each name the sections their record requires and read them through `section_gaps` in `src/irminsul/checks/sections.py`, which reports a required level-2 section that is absent, repeated, or, when the list says it must be substantive, empty apart from comments and marked prompts. `adr-structure` requires substance of `## Decision` alone, so a record may leave the other four to the template's comments; `rfc-structure` requires it of every owner's section its weight asks for, and does not report a repeated one.

## What a run consists of

Five enforcements are passes, in `PASSES` in `checks/pipeline.py` rather than in `REGISTRY`, so no `checks.enabled` list can leave one out. `co-change`, `diff-integrity` and `new-dependency` judge a change: they read its range from the graph and report nothing for a graph without one. `CHANGE_PASSES` names them, and a test fails when a pass that reads `DocGraph.change` is missing from it, so a run given no base can say which passes it did not make. `history-depth` judges the checkout, and `adoption-record` the record the ownership checks take their exceptions from; both scope themselves by the names of the checks the run is making. `run_checks` assembles every run that reaches a verdict — the selected checks, then the passes, then ignore comments, classes and the baseline — and `RunResult.failed` is the one rule that turns it into pass or fail. `irminsul check`, the [change](change.md) lifecycle gates, `context --after-edit` and the [MCP server](mcp-server.md)'s `check` tool each ask it for their run, so a run means the same thing wherever it is asked for; a view of one check's items, such as `irminsul fix` or `list undocumented`, takes that check through `run_check`, which reaches no verdict.
<!-- anchor: src/irminsul/checks/pipeline.py#CHANGE_PASSES @sha256:14a5db692c54 -->

**A check may delegate error reporting only where the calling execution path guarantees that the responsible validation runs.** `uniqueness` and `test-ownership` say nothing about an unreadable adoption record because the `adoption-record` pass reports it, and that holds only while every path runs the pass. So a test replaces every entry in `PASSES` with a sentinel and asserts each entry point fired all of them, and another reads the source so that nothing outside `checks/pipeline.py` calls a check's `run`.

The range every diff pass reads is resolved once, by `resolve_change_range` in `checks/change_range.py`, and carried on the graph: git supplies the merge base and the changed paths, and `after_text` and `after_paths` there give `co-change`, `diff-integrity`, `new-dependency` and the review queue the same after side — the working-tree text and the files git tracks or would add, or `HEAD` under `--committed-only` — while under `--source-diff` `source_changed_displays` in `adoption.py` reads each sibling source repository's own range. So this component depends on `git` and `adoption-record`.

**`diff-integrity` reads protection from the base, never from the change under review.** Which folders hold sealed records, where the baseline lives, and whether a claim governs its evidence all come from the merge base; otherwise a change could lower its own protection in one commit and edit freely in the next ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)). Every setting is sealed under its dotted name: `_SEALS` in `checks/diff_integrity.py` says which way each known setting weakens, and the schema is walked rather than listed, so a setting outside the map is still reported from the day it is added rather than sealed by somebody remembering to ([A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md)).
<!-- anchor: src/irminsul/checks/diff_integrity.py#_SEALS @sha256:6ad276a3058e -->

## RFC checks

`rfc-follow-through` asks a required-update doc for its `implements` back-link only once the driving RFC reaches `implemented`, because `rfc-lifecycle` rejects `implements:` on any RFC that has not ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)); asking earlier would tell an author, and `irminsul fix`, to write what the gate rejects. Between acceptance and finalization the pending work is already visible as `irminsul list lifecycle --queue`. For the same reason a `required_updates` entry of `kind: create` is missing only once the RFC is `implemented`: the doc is what the implementation writes. Finalization judges the RFC as implemented, so `required_update_findings` still blocks it while a doc it creates is absent.

`rfc-structure` judges only a draft or accepted RFC, because an implemented or rejected one is a sealed record and the layout is not asked of what was written before it existed. It never infers a weight from the body: an RFC with none, or an unknown one, is asked only for its weight, since a guess would demand sections its owner may not want. Its hint counts code spans with the reader `code-references` uses, in each paragraph above the first of `## Design detail`, `## Requirements`, `## Tasks` and `## Resolution`, with each list item a paragraph of its own; four in one paragraph says a list of names is probably in the owner's part, and it judges nothing about the prose ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)).

The rules `rfc-lifecycle`, `rfc-follow-through` and `change-binding` share with the [change](change.md) gate — a dangling `resolved_by`, a missing scaffolding section, a missing or unknown `affects` entry — are predicates in `src/irminsul/change/gate.py`, which is why this component depends on `change`: each check calls them with the RFC's own state and the gate with the state it judges, so a finding and the blocker for the same rule have one wording and one code.

## Source inventory and glob resolution

A run walks each scope once — the configured source roots, and the declared test roots under the same policy — and every check reads that walk from the graph's [source tree](docgraph.md) rather than walking for itself. Ownership has one matcher too: `claims_for` in `checks/uniqueness.py` matches `describes` patterns against files and scores their [specificity](../GLOSSARY.md#specificity) for `uniqueness`, both import checks, `co-change`, `context`, and the owner moves `diff-integrity` and `list review` compare across refs.

## Scope & Limitations

Checks do not apply fixes; `irminsul fix` remediates. They do not evaluate prose quality or writing style, and they do not modify source files or docs. Neither the source walk nor the doc walk follows a directory symlink.

`claim-provenance` reads the claims a doc declares and never the prose around them: no wording, however emphatic, asks for a claim ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)). Valid evidence shows a claim points at something real, not that the claim is true. Evidence drift is reported only for claims in stable `foundation` and `architecture` docs.

Two limits are deliberate, because each is a wide net on a finding that does not fail a default run, and narrowing one would report things that are not wrong, which is what teaches an author to reach for an ignore comment. `code-references` treats a name as defined when it appears as a whole identifier anywhere in a source file, so a name surviving only in a comment or a string still resolves. And a doc's freshness is its commit time, so a commit that touches a doc for any reason — a formatting sweep, a mass rename — resets `mtime-drift` and `stale-reaper` for it, and so does an uncommitted edit ([Git helpers](git.md)). Anchors are the precise instrument; the commit clock is the coarse net behind them.

`code-references` judges a code span in a doc's `summary:` at that doc, by that doc's rules: a live doc's summary is read and a decision record's or RFC's is not, as their bodies are not. It skips the generated table in `docs/AGENTS.md`, which repeats every summary and which `irminsul fix` rewrites, so a finding there could only name a sentence that lives, and can only be answered, in another doc.

## Implemented requirements

- **acknowledge-a-reviewed-co-change-or-evidence-drift#trailer-acknowledges-co-change** — A `co-change` warning on a doc SHALL NOT be reported as a warning when a commit in the diff range carries an `Irminsul-Reviewed: co-change <doc> reason="..."` trailer naming that doc with a non-empty reason, unless a later commit in the range changed one of the files the warning lists, and SHALL be reported as an info finding that quotes the reason. (provenance: code; [RFC](../rfcs/acknowledge-a-reviewed-co-change-or-evidence-drift.md))
  <!-- anchor: src/irminsul/checks/co_change.py#run_co_change @sha256:a3704bc0981d -->
- **acknowledge-a-reviewed-co-change-or-evidence-drift#acknowledgement-needs-reason** — A trailer without a reason, naming no doc, or naming a doc `co-change` does not warn on SHALL acknowledge nothing and SHALL be reported as an info finding. (provenance: code; [RFC](../rfcs/acknowledge-a-reviewed-co-change-or-evidence-drift.md))
  <!-- anchor: src/irminsul/checks/co_change.py#_read_trailers @sha256:71dffb4cecd6 -->
- **acknowledge-a-reviewed-co-change-or-evidence-drift#pin-suppresses-drift** — When a claim records a pin for an evidence file and the file's current normalized hash equals it, `evidence-drift` SHALL NOT report that file; when they differ, the file SHALL be judged by the commit-time comparison, as one without a pin is. (provenance: code; [RFC](../rfcs/acknowledge-a-reviewed-co-change-or-evidence-drift.md))
  <!-- anchor: src/irminsul/checks/claim_provenance.py#ClaimProvenanceCheck._scan_evidence_drift @sha256:6f8e532e5acf -->
- **a-gate-file-is-sealed-not-scored#gate-file-change-is-certain** — Under `--diff <base>`, when the merge base holds an Irminsul config or a baseline, `diff-integrity` SHALL report `diff-integrity/gate-file-changed` as a certain finding for each file under `.github/workflows/`, and each `action.yml` or `action.yaml`, that mentions `irminsul` at the base or at the head and differs between them. (provenance: code; [RFC](../rfcs/a-gate-file-is-sealed-not-scored.md)) <!-- irminsul:ignore code-references reason="the alternative spelling GitHub accepts, which this repository does not use" -->
  <!-- anchor: src/irminsul/checks/diff_integrity.py#_changed_gate_files @sha256:b5a77806e906 -->
- **a-gate-file-is-sealed-not-scored#decision-record-clears-gate-file** — A decision record added in the same change with `status: stable` whose `## Decision` section names a gate file's path in a code span SHALL clear that file's finding, and SHALL clear no other file's. (provenance: code; [RFC](../rfcs/a-gate-file-is-sealed-not-scored.md))
  <!-- anchor: src/irminsul/checks/diff_integrity.py#_accepted_decision_text @sha256:af3d09b7680d -->
- **a-gate-file-is-sealed-not-scored#adopting-change-is-not-sealed** — When the merge base holds neither an Irminsul config nor a baseline, `diff-integrity` SHALL NOT report `gate-file-changed`. (provenance: code; [RFC](../rfcs/a-gate-file-is-sealed-not-scored.md))
  <!-- anchor: src/irminsul/checks/diff_integrity.py#_adopting @sha256:666fe5decf75 -->
- **a-gate-file-is-sealed-not-scored#gate-scoring-removed** — `diff-integrity` SHALL NOT emit [`gate-weakened`](../decisions/a-change-may-not-lower-its-own-gates.md), [`filter-unreadable`](../decisions/a-change-may-not-lower-its-own-gates.md) or [`filter-not-compared`](../decisions/a-change-may-not-lower-its-own-gates.md), and `irminsul explain` SHALL report each as an unknown code. (provenance: code; [RFC](../rfcs/a-gate-file-is-sealed-not-scored.md))
  <!-- anchor: src/irminsul/checks/diff_integrity.py#_changed_gate_files @sha256:b5a77806e906 -->
- **an-rfc-has-an-owners-part-and-an-agents-part#an-rfc-declares-its-weight** — `rfc-structure` SHALL report `rfc-structure/missing-weight` for an RFC whose `rfc_state` is `draft` or `accepted` and whose frontmatter has no `weight`, or one other than `small` or `large`. (provenance: code; [RFC](../rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md))
  <!-- anchor: src/irminsul/checks/rfc_structure.py#RfcStructureCheck._weight_findings @sha256:20fad80547ad -->
  <!-- anchor: tests/test_checks_rfc_structure.py#test_no_weight_is_reported @sha256:6238c0676321 -->
- **an-rfc-has-an-owners-part-and-an-agents-part#an-owners-section-is-required** — `rfc-structure` SHALL report `rfc-structure/missing-section` for each owner's section the RFC's weight requires (Summary and Decisions for `small`; Summary, Problem, How it works, Cost and risk and Decisions for `large`) that is absent, or empty apart from HTML comments and placeholder lines, in an RFC whose `rfc_state` is `draft` or `accepted`. (provenance: code; [RFC](../rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md))
  <!-- anchor: src/irminsul/checks/rfc_structure.py#RfcStructureCheck._section_findings @sha256:42dfb23b1f83 -->
  <!-- anchor: tests/test_checks_rfc_structure.py#test_a_large_rfc_needs_all_five_owners_sections @sha256:155f503616df -->
- **an-rfc-has-an-owners-part-and-an-agents-part#the-owners-part-comes-first** — `rfc-structure` SHALL report `rfc-structure/section-out-of-order` for an owner's section heading below `## Design detail`, and for an RFC that has `## Requirements` but no `## Design detail`. (provenance: code; [RFC](../rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md))
  <!-- anchor: src/irminsul/checks/rfc_structure.py#RfcStructureCheck._order_findings @sha256:a254276f44af -->
  <!-- anchor: tests/test_checks_rfc_structure.py#test_an_owners_section_below_design_detail_is_out_of_order @sha256:19f411f5348d -->
- **an-rfc-has-an-owners-part-and-an-agents-part#a-dense-owners-paragraph-is-a-hint** — `rfc-structure` SHALL report `rfc-structure/dense-paragraph`, a hint, for a paragraph of the owner's part that holds four or more code spans, and SHALL NOT report one in the agent's part. (provenance: code; [RFC](../rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md))
  <!-- anchor: src/irminsul/checks/rfc_structure.py#RfcStructureCheck._dense_findings @sha256:80cc10739544 -->
  <!-- anchor: tests/test_checks_rfc_structure.py#test_a_paragraph_of_claim_ids_in_how_it_works_is_a_hint @sha256:590155ad6360 -->
