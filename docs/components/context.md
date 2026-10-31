---
id: context
title: Agent context command
status: stable
summary: What governs a path — owning doc, ranked tests, active RFCs and next commands before an edit, findings after it.
depends_on:
  - adoption-record
  - baseline
  - change
  - checks
  - config
  - docgraph
  - frontmatter
  - git
  - new-list-regen
  - user-errors
describes:
  - src/irminsul/context.py
  - src/irminsul/ranked_tests.py
owns_tests:
  - tests/test_cli_context.py
  - tests/test_context_statelessness.py
  - tests/test_context_test_ranking.py
  - tests/test_context_unit.py
  - tests/test_context_validation_states.py
claims:
  - id: context-is-stateless
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Context keeps no session — a call stores no task, selection, ownership result, or other repository-derived result for a later call to read, and every call derives those from the repository when it runs.
    evidence:
      - src/irminsul/context.py
      - src/irminsul/git/mtime.py
    pinned:
      src/irminsul/context.py: sha256:1623bcb557c4
      src/irminsul/git/mtime.py: sha256:c71794836a12
---

# Agent context command

`irminsul context` tells an agent what governs a file before and after it edits one: the doc that owns the path, the tests that doc declares and the ones that import the file, the dependencies that doc declares, active RFCs that affect it, and the next commands to run. After the edit it says less, because an edit's packet is about the change: each owning doc with the changed files it owns, and the findings the change caused. It is a runtime lookup over the current [DocGraph](docgraph.md), not a generated artifact, and it is a starting map rather than the documentation itself: its excerpts are bounded, so read the owning doc it names before changing code.

The command takes exactly one input mode, and `irminsul context --help` says what each takes: `<path...>` is the packet to read before editing, `--topic` finds the docs for a concept, and `--after-edit` maps the change made and is the one mode that runs checks. That change is the one `check --diff` judges ([A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md)). A source file under a configured root outside the repository, such as the sibling code repository of the [private-docs layout](../guides/private-docs.md), is named by the display spelling `describes:` uses, and its filesystem path maps to that spelling. A path that is not on disk yet is answered too, because that is when an agent asks which doc a new file belongs to: `_repo_relative` gives it the spelling it would have, the owner is the doc whose `describes` glob covers it, and `ContextResult.missing_inputs` (or `UnmatchedPath.missing`, where no glob does) says the file does not exist. A path outside the repository and every configured root is refused whether or not it exists.
<!-- anchor: src/irminsul/context.py#_repo_relative @sha256:5ce500137ae9 -->
<!-- anchor: src/irminsul/context.py#ContextResult.missing_inputs @sha256:244fe8cd607f -->
<!-- anchor: src/irminsul/context.py#UnmatchedPath.missing @sha256:7f726f922998 -->

A doc path is its own owner, and a test file reaches every doc that lists it in `owns_tests:` or `recommended_tests:`. A source file is owned by the doc whose `describes` glob matches it most specifically, scored by `claims_for`, the routine the `uniqueness` check reads. When two docs tie, the path has no owner: context lists both as candidates under "ambiguous ownership", and `uniqueness` reports the same tie as an error. A path nothing owns still lists the claims whose `evidence` names it, so an agent editing a file no component owns is told which contract binds the change. When the [adoption record](adoption-record.md) excepts such a path, `UnmatchedPath.recorded_debt` says so before the edit: a change that edits it must give it an owning doc in the same change, or `check --diff` fails with `diff-integrity/adoption-debt-touched`. After an edit, the files Irminsul writes and judges itself, which `_tool_files` names from `paths.baseline`, `paths.adoption` and `manifest_rel_path` (the manifest path [`irminsul fix`](new-list-regen.md) regenerates, read from there so the two cannot name different files), and the guidance files of `DocGraph.guidance_files` (the README, the agent guides and `paths.extra_docs`), are left out of the unmatched list unless a claim cites one, because no doc is meant to own them.
<!-- anchor: src/irminsul/context.py#UnmatchedPath.recorded_debt @sha256:ba5798ce6f3b -->

## Which tests a source file gets

A flat list of an owner's tests buries the one that exercises the file in hand, so for a source path the packet adds every test in `paths.test_roots` that imports the file, whichever doc owns it, and `Ranker.rank` orders them by evidence: tests that import the file, then tests by how many commits changed both, then the rest alphabetically. `ContextResult.test_reasons` keeps why each is named. An import is a direct import of the module, so a test that reaches it through a package re-export is not an importer.
<!-- anchor: src/irminsul/ranked_tests.py#Ranker.rank @sha256:252d7b905161 -->
<!-- anchor: src/irminsul/context.py#ContextResult.test_reasons @sha256:d4d118e24f76 -->

## Claims to review

A report's `claim_reviews` lists every claim whose `evidence` names a path in hand — a named path, or a changed one after an edit — except `follows-evidence` claims, where the code wins outright. Each carries a question that quotes the claim back at those files. It is a request to a reader, not a finding: the change reached the code a contract is written against, and only a reader can say whether the contract still holds, so it prints outside the findings, `--after-edit` exits 0 on it, and `check` never reports it. The signal is the change itself, an exact match on `evidence:`, so it does not go quiet once the doc is touched, as `claim-provenance`'s commit-time comparison can, and it reaches code the declaring doc does not own. `irminsul list review --changed` queues the same claims as `governing-claim` items.
<!-- anchor: src/irminsul/context.py#ContextReport.claim_reviews @sha256:c7754845d0d8 -->

## Active RFCs and next actions

The packet lists the active RFCs whose `affects` names the owner's id or whose `required_updates` names its doc path. Both are exact matches on authored frontmatter, and neither is transitive: an RFC affecting a component this one depends on, or a path child of it, does not appear. `rfc_state` must be `draft` or `accepted`, but supersession is not consulted, so a superseded draft still counts as active. Requirement prose is quoted, not matched against the edit: whether the edit meets a requirement is the agent's judgment, not a finding. The packet names a few RFCs and counts the rest by id, and its next actions are commands, each with a reason derived from the report's own state.
<!-- anchor: src/irminsul/context.py#ContextResult.active_changes @sha256:62a843d4c211 -->
<!-- anchor: src/irminsul/context.py#ContextReport.next_actions @sha256:48a958a14349 -->

## How the two modes pair

The two calls encode a stateless inspect–edit–verify loop. A context call keeps no
session: it stores no task, selection, or result for a later call to read, and every
call re-derives what it reports from the docs, the config, and git when it runs, so the
loop is safe to re-enter ([context keeps no session](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)). Git history is read once
per graph and each call builds its own, so a commit made between two calls reaches the
second. <!-- claim:context-is-stateless -->

`tests/test_context_statelessness.py` pins the observable half of that: within one
process, ownership moved between two calls reaches the second, a commit made between
two calls reaches the second, and three calls leave every file in the repository
byte-identical. What it cannot show is that no code path holds hidden state, so the
contract still needs a reader when the code changes. Listing it under `owns_tests:` routes
it to this document and makes `test-ownership` verify the file exists; nothing in Irminsul
executes a declared test, so only the project's own suite proves it passes.

What does outlive a call is an external check's cache of what it observed: with
`external-links` enabled, a call can report what a link returned earlier, and the finding
carries its observation time.

`--after-edit` exits non-zero when **this change** introduced errors, so the same
command doubles as a gate in a pre-commit hook or CI step without failing forever on
debt the change did not create. What counts as debt is the baseline's rule: a finding
from outside the check registry, or one auditing a suppression, is charged to the change
however long it has been there, as it is under `check --delta`. Where no trustworthy
baseline exists the repository verdict decides instead, which is the safe direction. The
pull-request gate is independent of this and still fails on the repository's own state.

The findings an edit reports are the ones this change caused: the comparison above, over
every severity, listed once for the whole report and not under each owner. When the change
could not be compared, every finding of the run is listed instead, and `validation.change`
says why, so a list that looks clean is never one nothing measured. Under those findings
the plain output lists the trailer each open one can take, under the heading `irminsul check`
uses, and the JSON gives each finding that trailer as `trailer`. The comparison counts a
finding by its fingerprint, so when a doc has the same finding twice and the count grew, the
first one in report order is taken as the old one. The finding named can then sit on the
line that did not change, and the verdict is still right: one more of them was introduced.

With no base, the change is the working tree against `HEAD` and the passes that judge a
change (`CHANGE_PASSES`) have no range to read, so they do not run. A `passed` verdict
then means no new finding from what did run, and `ChangeValidation.note` says so and
names `--base-ref <base>` for the whole branch and `--base-ref HEAD` for the uncommitted
work alone. The verdict itself is the same with or without the note: an edit to a file
the adoption record excepts passes here and fails under `--base-ref HEAD`.
<!-- anchor: src/irminsul/context.py#ChangeValidation.note @sha256:fdfc2efcbd75 -->
<!-- anchor: src/irminsul/checks/pipeline.py#CHANGE_PASSES @sha256:14a5db692c54 -->

## Content excerpts

Path reports carry authored content by default: the owning doc's first substantive block,
its `## Scope & Limitations` section, its claim text, and requirement prose from the active
RFCs that affect it. `--include` selects among these categories; `dependencies`, the direct
`depends_on` docs, is not in the default. A topic lookup and an after-edit report carry
content only when given `--include`.

The boundary excerpt is that one section and nothing else, and a doc that draws no
boundary contributes none rather than an empty one. It carries the section's caveats
verbatim, including a sentence saying a stated limit is not enforced — reading such a
limit as a rule the tool checks is the misreading the excerpt exists to prevent.

## Scope & Limitations

Topic search is deterministic per-term substring matching over doc metadata and heading texts, every term required, not fuzzy or semantic search. Prose under a heading is not searched, so a word that appears only in a body, such as a plural of a heading's word, finds nothing.

With a base, `--after-edit` reads the paths `changed_since` reports. A file moved without `git mv` reads as a deletion plus a new file until it is staged. With no base it reads the staged, unstaged, and untracked paths from `git status`, which is also the fallback for a repository with no commits and for a project below its git root, where there is no history of its own to diff; outside a git worktree it reports the git error instead of guessing. <!-- anchor: src/irminsul/git/changes.py#working_tree_changed_paths @sha256:86b253bf9d54 -->

Test ranking is evidence of relation, not of coverage: nothing runs a test, and one that imports a file or changed with it may not exercise the change in hand. Only Python imports are read, so a test in another language ranks by history alone, and the history count follows no rename and skips merge commits.

Content extraction does not rank relationships, estimate tokens, perform semantic search, or persist session state; those remain separate retrieval concerns.
