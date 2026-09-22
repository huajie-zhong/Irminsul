---
id: context
title: Agent context command
status: stable
summary: Runtime map of what governs a path — owning doc, recommended tests, dependencies, active RFCs, findings, and next commands — for the start and end of an edit.
depends_on:
  - baseline
  - change
  - checks
  - config
  - docgraph
describes:
  - src/irminsul/context.py
owns_tests:
  - tests/test_cli_context.py
  - tests/test_context_statelessness.py
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
---

# Agent context command

`irminsul context` tells an agent what governs a file before and after it edits one: the doc that owns the path, the tests and dependencies that doc declares, active RFCs that affect it, relevant findings, and the next commands to run. It is a runtime lookup over the current [DocGraph](docgraph.md), not a generated artifact, and it is a starting map rather than the documentation itself: its excerpts are bounded, so read the owning doc it names before changing code.

The command supports exactly one input mode:

- `irminsul context <path>` for a source or doc path. A path inside the invocation root is named repo-relative; a source file under a configured root *outside* it — the sibling code repo of the [private-docs layout](../guides/private-docs.md) — is named by its source-root-relative display spelling, the same one `describes:` and `claims[].evidence` use. Its filesystem path (`../code/src/core.py`) also works: an existing file under a configured external root is mapped to that display spelling. Only a path that neither lies in the repo nor sits under a configured root is refused as outside the repo
- `irminsul context --topic "<query terms>"` for deterministic tokenized search over doc id, title, path, `describes`, `tests`, `tags`, and `summary`: every whitespace-separated term in the query must appear as a substring somewhere in that set (terms may hit different fields), so a multi-word query need not match as one literal phrase
- `irminsul context --changed` for staged, unstaged, and untracked git files

Each result reports the owning doc, matching source claims, first declared entrypoint, tests, `depends_on`, docs that depend on it, relevant deterministic findings, and next command hints. Hints are derived from that result's own relevant findings using the same finding-to-fix mapping the [findings surfaces](checks.md) use, so a `fix` invocation is offered only when the owning check actually harvests a fix for that finding; the `irminsul check` gate is always the terminal hint. `--profile enabled|all-available` controls deterministic finding breadth, and both ordinary lookups and workflow aliases default to `enabled`.

A source path is owned by the doc whose `describes` glob matches it most specifically, scored the same way the `uniqueness` check scores it. When two docs tie, the path has no owner: context lists both as candidates under "ambiguous ownership", and `uniqueness` reports the same tie as an error.

Ownership is not the only way a document reaches a file. A path no `describes` glob matches is still reported as unmatched, but if a `claims[].evidence` entry names it, context lists those claims under `governed_by` with the claim's id, relation, text, and the document that declares it. `action.yml` is the case this exists for: no component owns it, yet [architecture overview](../architecture/overview.md) declares a `governs-evidence` claim citing it, so an agent editing it is told which contract binds the change without a component being invented to hold the file.

## Claims to review

Alongside the results, a report carries `claim_reviews`: every claim in the tree whose
`evidence` names one of the paths in hand — the paths named in `path` mode, the changed
paths in `changed` mode, none in `topic` mode. Each entry carries the claim's id,
relation and text, the declaring document, the evidence paths this call is about, the
decision records linked from the paragraphs carrying that claim's `claim:<id>` marker,
the declaring document's `tests:`, and a question that quotes the claim back at the
changed files.

The question differs by relation, because the two relations addressed here ask different
things. A `governs-evidence` claim asks whether the code still satisfies the sentence,
and says that if they disagree the code is what is wrong. A `review-on-divergence` claim
asks whether the two still agree, and says that neither wins by default: decide which one
is wrong, correct that one, and say why.

It is a request to a reader, not a finding. Nothing here says the claim is broken and
nothing mechanical could: what it says is that the change reached the code a contract is
written against, so somebody has to decide whether the contract still holds. That is
why it prints outside the findings list and says so, why `--after-edit` still exits 0 on
it, and why `check` never reports it.

Three properties are the point:

- **The signal comes from the change, not from a clock.** Membership is the exact-string
  test `evidence:` is authored in, applied to the paths this call is about.
  `claim-provenance` compares commit times and can go quiet once a document is touched
  for any reason; this does not read history at all.
- **Editing the document does not clear it.** A changed doc is not evidence that anyone
  re-read the contract in it, so the entry appears whether or not the doc changed. The
  separate `co-change` line answers the different question of whether the doc shipped
  with the code.
- **A claim reaches code its own document does not own.** `checks-consume-the-graph` in
  [architecture overview](../architecture/overview.md) cites `src/irminsul/docgraph.py`,
  which [docgraph](docgraph.md) owns. Editing that file surfaces the claim even though
  the owning document never mentions it.

A queued claim is printed here and not also under `content`'s `claims` category, nor on
the terse `governed by` line under an unmatched path. One claim asks its question once.
A claim the paths in hand do not cite stays an ordinary content excerpt.

`follows-evidence` is the one relation left out: there the code wins outright, so
changing it settles the question instead of raising one and a prompt would be noise. That
also makes it the only relation still shown on the terse `governed by` line under an
unmatched path. The same queue is available from
[`irminsul list review --changed`](new-list-regen.md), which lists these as
`governing-claim` items.

The block is not bounded the way content excerpts are. An excerpt is orientation, so
clipping it costs a reader nothing they cannot get by opening the document; a queued
claim is a question somebody has to answer, and dropping the ninth one would leave a
claim unreviewed — which is the failure this exists to prevent.

## Editing workflow

The common agent loop is expressed as two stateless workflow aliases over those
input modes:

- `irminsul context --before-edit <path...>` resolves one or more source or doc
  paths in one graph pass, groups them by owner, and adds active draft/accepted
  RFCs whose explicit `affects` list names that owner's id or whose
  `required_updates` names its doc path. Both are exact matches on authored frontmatter,
  and neither is transitive: an RFC affecting a component this one depends on, or a path
  child of it, does not appear. `rfc_state` must be `draft` or `accepted` — `implemented`
  and `rejected` are left out — but supersession is not consulted, so a superseded draft
  still counts as active. At most eight are named, in doc-path order, with a count of the
  rest and each of their ids, which `irminsul change status <rfc-id>` resolves; that order
  is deterministic, not a relevance ranking, and nothing here claims one. The ids are
  carried because a count is not retrievable: the pointer used to read `irminsul list
  lifecycle`, which lists lifecycle findings and the accepted backlog, and an omitted
  `draft` appears in neither. Claim reviews are deliberately not
  capped: an RFC list is supporting material, a governing claim is an obligation. Parsed requirements and declared tests are
  included without inferring relationships from prose; whether the edit meets a
  requirement is for the agent to judge, not a finding. It runs **no checks**: it
  reports what to read before an edit that has not happened, and a check pass over the
  whole tree says nothing about a file nobody has touched. Its `validation` is
  `not_run` and its per-result `findings` are `null`, never `[]`.
- `irminsul context --after-edit` inspects staged, unstaged, and untracked paths,
  routes both owned source files and explicitly declared tests, and runs the
  enabled checks even if no changed path has an owner.

Workflow JSON keeps the underlying lookup `mode` (`path` or `changed`) and adds
`workflow`, `validation`, per-result `active_changes`, and ordered
`next_actions`; ordinary context calls omit those fields. The actions are explicit
command-and-reason pairs derived from report state, not an interactive session or
an AI recommendation.

## How the two modes pair

The aliases encode a stateless inspect–edit–verify loop. A context call keeps no
session: it stores no task, selection, or result for a later call to read, and every
call re-derives what it reports from the docs, the config, and git when it runs, so the
loop is safe to re-enter ([context keeps no session](../decisions/context-keeps-no-session-external-checks-may-cache-observations.md)). Git history is read once
per graph and each call builds its own, so a commit made between two calls reaches the
second. <!-- claim:context-is-stateless -->

`tests/test_context_statelessness.py` pins the observable half of that: within one
process, ownership moved between two calls reaches the second, a commit made between
two calls reaches the second, and three calls leave every file in the repository
byte-identical. What it cannot show is that no code path holds hidden state, so the
contract still needs a reader when the code changes. Listing it under `tests:` routes
it to this document and makes `coverage` verify the file exists; nothing in Irminsul
executes a declared test, so only the project's own suite proves it passes.

What does outlive a call is an external check's cache of what it observed. When
`external-links` is enabled, a link whose cached result has not expired is not requested
again, so a context call can report what the link returned earlier rather than what it
returns now. The findings say so: a cached result carries its observation time, and a run
that used the cache adds an `external-links/cached-results` notice.

| | `--before-edit <path...>` | `--after-edit` |
|---|---|---|
| Input | paths you name, resolved through `path` mode | staged/unstaged/untracked paths, via `changed` mode |
| Owner routing | doc paths match directly; source paths match the most specific `describes` glob | same, plus files listed in a doc's `tests:` route to that doc |
| Default profile | `enabled` | `enabled` |
| Checks | not run | run over the whole tree, plus a second pass at the baseline |
| Exit code | 1 when no named path has an owner or a path does not exist; 2 for a path outside the repo | 1 when this change introduced errors, or — when no baseline could be established — when the repository has any |
| Purpose | load the packet **before** you touch code | say what this change broke, and what it inherited |

Both modes attach the deterministic next step. `--before-edit` always closes
with a pointer to `--after-edit`. `--after-edit` adds a `co-change` reminder and
a `irminsul context <owner-doc>` action for each result whose owning doc was not
edited in the same change — including a result reached only through a declared
test file — plus `irminsul check` when either verdict reports errors, worded to say
which. In both modes,
an input path that is configured source with no deterministic owner adds
`irminsul list undocumented --all`, and active draft/accepted RFCs that name an
owner surface with a `irminsul change status <id>` action ([change lifecycle](change.md)).

## Example: the edit loop end to end

Suppose an agent is about to change `src/irminsul/context.py`. It packages the
owning knowledge first (`...` marks lines left out here):

```console
$ irminsul context --before-edit src/irminsul/context.py
Workflow: before-edit

owner: context (docs/components/context.md)
  ...
  tests: tests/test_cli_context.py, tests/test_context_unit.py, ...
  depends_on: checks (...), config (...), docgraph (...)
  depended-on-by: cli (...), mcp-server (...)
  active changes:
    example-change [accepted] (docs/rfcs/example-change.md)
      requirements: bounded-excerpts, ...
  content:
    [owner] Agent context command (docs/components/context.md)
      reason: Owns the requested path through document 'context'.
      `irminsul context` tells an agent what governs a file before and after it edits one: ...
    [boundary] Scope & Limitations (Agent context command) (docs/components/context.md)
      reason: What the owning document says this component does not do.
      Topic search is deterministic per-term substring matching ...
    [claims] Claim context-is-stateless (invariant) (docs/components/context.md)
      reason: Structured claim declared by the owning document.
      Context keeps no session — ...
    ...
  findings: not checked (run `irminsul check`)
  hints:  (none)

Repository validation: not run (no checks were executed)
Change validation: not run
  reason: before-edit does not run the checks; run `irminsul context --after-edit` once the edit is made, or `irminsul check` for the tree as it stands
Next actions:
  irminsul change status example-change
    reason: Active RFC explicitly affects component 'context'.
  irminsul context --after-edit
    reason: Validate the working tree and affected repository knowledge after editing.
```

The agent now knows which doc owns the file, which tests that doc recommends running,
that an active RFC affects it, which contract the owning doc declares, and exactly what to
run next. The excerpts tell it what to read in full; they do not replace reading
it. After editing the code — but forgetting to update the owning doc — it runs the
paired verify:

```console
$ irminsul context --after-edit
Workflow: after-edit

owner: context (docs/components/context.md)
  title: Agent context command
  input: src/irminsul/context.py
  ...
  co-change: owning doc not updated in this change
  findings: (none)
  hints: irminsul check

Repository validation: passed (0 errors, 0 warnings)
Change validation: passed (0 new errors vs HEAD)
Next actions:
  irminsul context docs/components/context.md
    reason: Owning document 'context' was not updated in this change.
```

`after-edit` exits non-zero when **this change** introduced errors, so the same
command doubles as a gate in a pre-commit hook or CI step without failing forever on
debt the change did not create. Where no trustworthy baseline exists the repository
verdict decides instead, which is the safe direction. The pull-request gate is
independent of this and still fails on the repository's own state. Add `--format json`
to either call to drive the loop from a script; the workflow fields
(`workflow`, `validation`, `active_changes`, `next_actions`) are additive over
the ordinary context JSON.

## Content excerpts

Workflow packets include authored content by default: the owning document's
first substantive prose block, its `## Scope & Limitations` section, its
structured claim text, and requirement prose from active RFCs that explicitly
affect it. Each excerpt identifies its category, source doc/path, title,
inclusion reason, and whether it was truncated, so an agent can use the content
without guessing why it appeared.

The boundary excerpt is that one named section and nothing else: a document's
other sections stay unquoted, and a document that draws no boundary contributes
no boundary excerpt rather than an empty one. It carries the section's caveats
verbatim, including a sentence saying a stated limit is not enforced — reading
such a limit as a rule the tool checks is the misreading the excerpt exists to
prevent.

`--include` accepts a comma-separated selection of `owner`, `boundary`,
`claims`, `requirements`, and `dependencies`; `all` selects every category and
`none` suppresses content. Primitive path/topic/changed lookups remain metadata-only
unless this flag is supplied. `dependencies` means direct authored `depends_on`
relationships and is not part of the workflow default.

Excerpts orient; they are not the documentation. Each excerpt and the number of
excerpts per owner are bounded so the first packet stays short, and an agent that
needs more reads the doc the packet names. The bounds are constants in
`src/irminsul/context.py`. Which items survive the count bound is fixed rather than
ranked: owner, boundary, claims in authored order, active RFCs by path with
requirements in authored order, then dependencies by path. A clipped excerpt reports `truncated`,
and the JSON `content.omitted` map counts eligible items the bound left out, so a
caller can tell a complete packet from a clipped one.

## Scope & Limitations

Topic search is deterministic per-term substring matching (every term must hit, in any field), not fuzzy or semantic search; matches rank by exact-id match, then whole-phrase hit, then how many distinct fields the terms covered. The per-term match is a plain lowercase substring test. The two phrase comparisons used for ranking lowercase both sides and treat any run of characters other than letters and digits as one space, so `claim-anchor` and `claim anchor` rank as the same phrase.

`--changed` and `--after-edit` read staged, unstaged, and untracked paths from `git status`; outside a git worktree they report the git error instead of guessing. <!-- anchor: src/irminsul/git/changes.py#working_tree_changed_paths @sha256:f07afa94e203 -->

Content extraction does not rank relationships, estimate tokens, perform semantic search, or persist session state; those remain separate retrieval concerns.
