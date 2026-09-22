---
id: change
title: Change lifecycle
status: stable
depends_on:
  - checks
  - config
  - docgraph
  - frontmatter
describes:
  - src/irminsul/change/**
owns_tests:
  - tests/test_change_finalize.py
  - tests/test_change_footprint.py
  - tests/test_change_impact.py
  - tests/test_change_readiness.py
  - tests/test_change_relations.py
  - tests/test_change_report.py
  - tests/test_change_transition.py
  - tests/test_cli_change.py
  - tests/test_requirements_parser.py
  - tests/test_tasks_parser.py
claims:
  - id: transition-applies-human-decisions
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: change transition writes only the two states a human decides, accepted and rejected; implemented is written exclusively by change finalize.
    evidence:
      - src/irminsul/change/transition.py
      - src/irminsul/change/finalize.py
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - change status
      - change verify
      - change transition
      - change graph
---

# Change lifecycle

The `irminsul change` command group treats an RFC as the forward artifact for significant change ([Change lifecycle](../decisions/change-lifecycle.md)): a work item that moves through `draft -> accepted -> implemented`, with `rejected` as the alternate terminal state. The module owns the read-only reports and the confirmed decision transition; the RFC document itself stays the single authored source of intent.

Two linked rules shape every report:

1. **Derive what is mechanically knowable.** Changed files, owning components, test evidence, and check findings come from the diff and the [DocGraph](docgraph.md) on every call; they are never copied onto the RFC.
2. **Expose evidence for semantic judgment.** Whether an implementation satisfies its intent is not derivable. Reports separate mechanical *blockers*, derived *evidence*, and *semantic-review clues* — and may say `mechanically_ready_for`, never "behavior is correct".

## Commands

- `irminsul change status <id>` — lifecycle state, declared `affects`, valid next transitions, a compact evidence summary, and next actions.
- `irminsul change verify <id> [--base-ref REF]` — the full read-only report: blockers, per-file evidence, declared-vs-derived scope divergence, and semantic-review clues, as plain text or versioned JSON.
- `irminsul change transition <id> accepted|rejected [--resolved-by <adr-path>] --confirm` — validate and apply a human-authorized decision atomically: `rfc_state`, `status: stable`, `resolved_by` (from `--resolved-by`, for acceptance), an empty `required_updates`, and the terminal scaffolding section land in one confirmed pass, reusing the dry-run/confirm contract of `fix`. `implemented` is deliberately not a valid target here; only finalization may write it.
- `irminsul change graph [<id>] [--relation all|dependency|supersession]` — derive the repository RFC graph or the complete connected component around one RFC ([Change lifecycle](../decisions/change-lifecycle.md)). Dependency edges come directly from `depends_on`; replacement edges come from the successor's `supersedes`, with reverse successors derived rather than written onto an old implemented RFC. Plain and versioned JSON output retain dangling edges, canonicalize lifecycle aliases, preserve missing lifecycle state as JSON `null`, and expose cycles, self-reference, multiple effective successors, and implemented-before-dependency contradictions without mutating files or changing the command's success exit. `--relation` filters both traversal and analysis.
- `irminsul change impact <id> [--base-ref REF]` — the derived, layered view ([Change lifecycle](../decisions/change-lifecycle.md)): where the change reached (foundation, architecture, components, guides, decisions, rfcs, surfaces, glossary), each observation with its source (declared field, diff path, graph edge, surface extractor, or finding) and a grounded review question. Two evidence levels — *plan* impact from declared scope and graph links alone, *observed* impact when a diff resolves; a missing baseline is stated as plan-level, never rendered as an empty observed impact. Surface kinds come from the extractor registry plus the repo's configured generic inventory rules, and an extractor that fails says so rather than dropping its kind — a layer is never silently empty. Output defaults to layers with actual evidence; `--all-layers` includes the empty ones. `change status` and `change verify` embed a terse per-layer summary.
- `irminsul change finalize <id> --anchor <req>=<path>#<symbol> --confirm` — the only transition to `implemented` ([Change lifecycle](../decisions/change-lifecycle.md)). It verifies the mechanical preconditions (accepted state, resolved ADR, reconciled scope, usable baseline, no errors from the enabled checks, required updates), presents the remaining semantic-review clues from the same read-only report `change verify` prints, then promotes every code-backed requirement into its owning component doc as an anchored claim with stable id `<rfc-id>#<requirement-id>`, adds the component's `implements` backlink, and flips `rfc_state` only after every component-doc write succeeded. Which symbol satisfies a requirement is a semantic judgment code cannot infer — the `--anchor` bindings are explicit, confirmed input, and an ambiguous owner (after the most-specific-claim rule has resolved nesting) requires `--owner <req>=<component>`. Promotion is idempotent: a claim id already present in the owner doc is skipped — the `implements` backlink is still ensured, so a hand-migrated claim never leaves the RFC without its inbound edge — and re-running against an identical implemented RFC writes nothing. The resulting anchor is a freshness tripwire, not proof of behavior.

Finalization flips `rfc_state: implemented` after component promotions, in the
implementation's own pull request. Once the protected branch records that state, the
proposal is immutable: under `--diff`, `diff-integrity` reports an edit or removal of
the record ([Git history seals implemented records](../decisions/git-history-seals-implemented-records.md)), so a
later behavior extension belongs in a new RFC rather than an edit to the implemented
record ([Change lifecycle](../decisions/change-lifecycle.md)).

## Requirements as review contracts

Behavior-changing RFCs carry a `## Requirements` section ([Change lifecycle](../decisions/change-lifecycle.md)): requirement blocks with a stable local id, an evidence obligation (`Provenance: code|adr|citation`), SHALL/MUST behavior text, and named WHEN/THEN scenarios. A maintenance RFC instead writes the explicit sentence `No new behavioral requirements: ...` — reviewable intent, not silent omission. Reports surface each requirement with its globally addressable id `<rfc-id>#<requirement-id>`; a `Provenance: code` requirement stays an unbound evidence obligation until finalization binds it to an anchored claim. Grammar findings are warnings while drafting and blockers at `change transition ... accepted`.

## Tasks and implementation evidence

An RFC records its accepted implementation plan as a static `## Tasks` list ([Change lifecycle](../decisions/change-lifecycle.md)): ordinary list items with stable ids that reference a requirement id or a declared affected component — never assignees, deadlines, or status fields. `change status` and `change verify` gather the mechanical evidence around each task: changed source owned by the referenced components, changed files named by those docs' `recommended_tests:`, and a review clue when evidence is absent. Counts are named precisely (`2/3 tasks with source evidence`, `2/3 with changed tests`), never rendered as percent complete: changed files are evidence, not proof that a free-text task is done. A changed test is the weakest of the three — Irminsul runs nothing, so it says a recommended test file was edited, never that it ran, passed, or covers the task beside it. The JSON names it `changed_tests` and `with_changed_tests`; the older `test_evidence` and `with_test_evidence` keys carry the same values for readers written against them. Irminsul does not implement tasks — the agent inspects the evidence, edits, and re-runs the report.

Evidence obeys the same never-guess rule as the baseline it is derived from. When no baseline resolves there is nothing to measure, so every task reports `unknown`, the summary counts are omitted, and the JSON carries `evidence_measured: false` with null evidence lists — an unmeasured task must never read as an unstarted one. The task grammar is enforced rather than filtered: a bullet with no backticked id, more than one reference, an empty reference, or text trailing its reference is a finding, and a `## Tasks` section that yields no parseable item is `empty-tasks`. A plan that fails to parse is reported, never silently reduced to `0/0`.

## Binding readiness and the agent loop

Readiness is composition, not a new invariant ([Change lifecycle](../decisions/change-lifecycle.md)). `change verify` reports `mechanically_ready_for: accepted|implemented|none` — never `semantically_correct` — by composing the lifecycle gates: pre-acceptance needs valid shape, explicit `affects`, and the requirements contract; pre-finalization additionally needs a usable baseline, reconciled scope (no touched-but-undeclared component and no changed source without a component claim), resolvable and fresh anchors in the affected component docs, and this RFC's required updates resolved. The pre-finalization gate is deliberately the same set `change finalize` enforces, so verify can never report ready for a tree finalization would refuse.

Findings are partitioned by their relationship to the change, and nothing is dropped in between. Every error an enabled check reports after the baseline is a blocker, because it would fail `irminsul check` too; a finding already promoted to a more specific blocker is not repeated. Every warning either lands in `scoped_findings` — it concerns the RFC, a declared component doc, or a changed path, and is rendered under *findings about this change* — or is counted per check under `repository_debt` (*unrelated*), visible but never a barrier to someone else's transition.

`irminsul new rfc` runs the repository-level binding-readiness summary first: errors, which are certain findings, block drafting, unless `--force` is passed; drift clues (stale anchors, lifecycle debt) print without blocking. `irminsul list lifecycle --queue` includes accepted-but-not-implemented RFCs with their next mechanical action, and the read-only reports are exposed over MCP (`change_status`, `change_verify`, `change_impact`, `binding_readiness`) while lifecycle writes stay confirmed CLI actions — see the [MCP server](mcp-server.md).

An RFC without `rfc_state` is a certain `rfc-lifecycle/missing-rfc-state` error and is listed
as `classify` work in the lifecycle queue until someone declares its state in
frontmatter. Ordinary `change` commands reject an RFC whose lifecycle state is absent.

## Diff baseline

Evidence needs a comparison range, and the resolver never guesses a clean result: an explicit `--base-ref`, a CI-provided base ref (`IRMINSUL_BASE_REF` or `GITHUB_BASE_REF`), or the local staged/unstaged/untracked set — in that order. When none is available the baseline is reported as `unknown`, which can never be mechanically ready for finalization.

Changed and deleted source paths use the same configured source policy as the on-disk inventory. A deletion that matches `.gitignore` or `source_excludes` therefore does not appear as owned or undocumented source merely because the file is no longer available to the walker.

## Scope & Limitations

The module does not implement tasks, judge semantic completion, or transition an RFC on its own conclusions — acceptance and rejection are human decisions it validates and records. The declared-versus-derived footprint comparison is shared with the `change-binding` check registered in [checks](checks.md).
