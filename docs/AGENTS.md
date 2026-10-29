# Agent Navigation Manifest

`irminsul fix` writes the table below from each doc's `summary:`; the rest of this
file is curated and survives it.

## Documentation Tree

<!-- agents-manifest:generated-start -->

### architecture

| ID | Doc | Summary |
|----|-----|---------|
| `architecture` | [Architecture](architecture/INDEX.md) | The shape of the system: which layers exist, how parts compose, what tools render or check it. |
| `check-pipeline` | [Check Pipeline](architecture/check-pipeline.md) | How `irminsul check` flows from invocation to exit code. |
| `component-hierarchy` | [Component Hierarchy and Doctrine](architecture/component-hierarchy.md) | How components nest. |
| `layers` | [Layers](architecture/layers.md) | The six layers and the rules each sets. |
| `overview` | [Architecture overview](architecture/overview.md) | High-level picture of CLI → DocGraph → Checks → CI. |

### components

| ID | Doc | Summary |
|----|-----|---------|
| `adoption-record` | [Adoption record](components/adoption-record.md) | The files that had no owning doc on the day of adoption, excepted from the ownership finding; it only shrinks. |
| `anchors` | [Anchored prose claims](components/anchors.md) | Anchored prose claims pinned to code. |
| `baseline` | [Baseline ratchet](components/baseline.md) | Records existing certain findings so CI fails only on new ones; it shrinks, and grows only by decision. |
| `change` | [Change lifecycle](components/change.md) | Bound-change lifecycle reports and transitions for RFCs. |
| `checks` | [Checks](components/checks.md) | Registered checks; exact names live in `src/irminsul/checks/__init__.py`. |
| `cli` | [CLI](components/cli.md) | CLI entry point. |
| `components` | [Components](components/INDEX.md) | Each architectural piece of Irminsul has a dedicated doc here. |
| `config` | [Config](components/config.md) | `irminsul.toml` schema. |
| `context` | [Agent context command](components/context.md) | What governs a path — owning doc, ranked tests, active RFCs and next commands before an edit, findings after it. |
| `docgraph` | [DocGraph](components/docgraph.md) | The in-memory model of the docs tree every check receives, and the one reader of fences and marked regions. |
| `file-writing` | [File writing](components/file-writing.md) | Writing files whole or not at all, in their own line endings, from templates in one strict environment. |
| `frontmatter` | [Frontmatter](components/frontmatter.md) | Per-doc YAML frontmatter parser/validator. |
| `git` | [Git helpers](components/git.md) | Git helpers for changed paths, commit times, and blame. |
| `init` | [Init scaffolder](components/init.md) | Scaffolding command and templates. |
| `languages` | [Language profiles](components/languages.md) | Language-profile registry. |
| `mcp-server` | [MCP server](components/mcp-server.md) | Read-only MCP stdio server that lets AI agents query the doc graph natively instead of shelling out to the CLI. |
| `new-list-regen` | [New / List / Fix commands](components/new-list-regen.md) | `new`, `list`, and `fix` commands, and the agent manifest `fix` rewrites. |
| `orient` | [Agent orientation command](components/orient.md) | The first call for agents — repo structure, doc totals, source ownership coverage, entry docs and commands as one report. |
| `refs` | [Refs backlink query](components/refs.md) | Every doc and guidance file that names or links to a doc or a Markdown file, from the current DocGraph. |
| `seed` | [Seed command](components/seed.md) | Capture starting intent into the foundation docs. |
| `surface` | [Surface extraction & on-demand derivation](components/surface.md) | Code surfaces derived on demand. |
| `user-errors` | [User errors](components/user-errors.md) | The one error type a command reports as a message and exit status, shared by CLI and MCP server. |

### decisions

| ID | Doc | Summary |
|----|-----|---------|
| `a-baseline-holds-certain-findings-and-grows-only-by-decision` | [A baseline holds certain findings and grows only by decision](decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md) | The baseline records only certain findings a check reports, is created once, loses entries as they are fixed, gains them only in a change that adds a decision record naming it, and shows what it hides. |
| `a-change-is-judged-from-its-merge-base-to-the-working-tree` | [A change is judged from its merge base to the working tree](decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md) | A change runs from the merge base, read with its own configuration, to the working tree, unless `--committed-only` stops it at HEAD; a reviewed co-change warning is acknowledged by a commit trailer. |
| `a-change-may-not-lower-its-own-gates` | [A change may not lower its own gates](decisions/a-change-may-not-lower-its-own-gates.md) | Under --diff every config setting and every gate file is compared with the merge base, a weakening is certain or a hint by what it does, and only a decision record the change adds, naming what it weakens, clears it. |
| `agents-get-stateless-read-only-queries-and-one-written-loop` | [Agents get stateless read-only queries and one written loop](decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) | Agents query the repository through read-only commands and an MCP server that keep no session, follow one edit loop written in a marked section of the root AGENTS.md, and get harness wiring scaffolded at adoption. |
| `authority-follows-the-kind-of-claim` | [Authority follows the kind of claim](decisions/authority-follows-the-kind-of-claim.md) | Code is authoritative for mechanically reconstructable state, not intent; a claim's relation decides who wins a disagreement, protection is read from the base, and a declaration about surviving code is not removed silently. |
| `ci-runs-each-gate-once-and-the-action-takes-typed-inputs` | [CI runs each gate once, and the Action takes typed inputs](decisions/ci-runs-each-gate-once-and-the-action-takes-typed-inputs.md) | CI installs from the lock, runs the self-check once per event with hints failing, tests four legs with a coverage floor on one, and installs the built wheel; the Action takes typed inputs only. |
| `code-is-named-in-code-spans-and-bound-by-anchors` | [Code is named in code spans and bound by anchors](decisions/code-is-named-in-code-spans-and-bound-by-anchors.md) | A code span is a literal mention checked against the tree, a bare `.md` name in plain text must be a link, and an anchor binds a paragraph to the definition it describes, pinned by a hash of its syntax tree; unbound names are queued for review. |
| `decisions` | [Architecture decisions](decisions/INDEX.md) | ADRs are the canonical home for why; this index gives their template and the rules every record follows. |
| `derive-facts-and-leave-meaning-to-the-reader` | [Derive facts and leave meaning to the reader](decisions/derive-facts-and-leave-meaning-to-the-reader.md) | Facts reconstructable from code are derived on demand and never committed, docs curate intent that inventories keep honest, and prose is selected for a reader by facts alone, never by a word list. |
| `docs-are-atoms-in-six-layers-and-code-has-one-owner` | [Docs are atoms in six layers, and code has one owner](decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md) | Docs are frontmatter-validated atoms in six configurable layers, each stating its own one-liner, folders own their docs, retired fields are errors, and every source file in documented territory has exactly one owning doc. |
| `finding-classes-decide-what-blocks` | [Finding classes decide what blocks](decisions/finding-classes-decide-what-blocks.md) | Every check is deterministic and every finding code is certain, hint or time; certain findings block unless a draft excuses one as unfinished, hints are investigated, and time findings stay off a diff. |
| `init-adopts-in-two-layouts-and-seed-fills-two-docs` | [Init adopts in two layouts, and seed fills two docs](decisions/init-adopts-in-two-layouts-and-seed-fills-two-docs.md) | `irminsul init` adopts existing code or starts fresh in one of two layouts, same-repo or siblings, and `irminsul seed` fills only the principles doc and the architecture overview with the project's starting intent. |
| `one-command-per-question-and-one-rule-per-flag` | [One command per question, and one rule per flag](decisions/one-command-per-question-and-one-rule-per-flag.md) | Each question has one command and each flag one meaning; maintenance writes are their own commands, a removed option names its replacement, exit 2 means the invocation was wrong and exit 1 that the command refused. |
| `rfcs-have-four-states-and-git-history-seals-decided-records` | [RFCs have four states, and git history seals decided records](decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md) | Records are named by slug and have a fixed shape, an RFC opens with an owner's part and moves through four states that repository evidence can contradict, the change commands judge its scope, the protected branch's history seals implemented RFCs and accepted decisions, and retirements are tombstones. |
| `surface-rules-and-language-profiles-are-data` | [Surface rules and language profiles are data](decisions/surface-rules-and-language-profiles-are-data.md) | Code surfaces come from built-in framework packs and project rules that share one record, checks read a kind's capabilities rather than its name, and a language profile is the one list of its language's files. |

### foundation

| ID | Doc | Summary |
|----|-----|---------|
| `anti-patterns` | [Anti-Patterns](foundation/anti-patterns.md) | What the system explicitly refuses. |
| `enforcement` | [Mechanical Enforcement](foundation/enforcement.md) | How documentation rules become deterministic checks, which findings block and which advise, and why CI rather than local tooling is where they hold. |
| `foundation` | [Foundation](foundation/INDEX.md) | Why the system exists, what it commits to, and the rules that don't bend. |
| `principles` | [Principles](foundation/principles.md) | The five core principles and the three laws of maintenance. |

### guides

| ID | Doc | Summary |
|----|-----|---------|
| `agent-protocol` | [Agent lifecycle protocol](guides/agent-protocol.md) | How an agent acts on a finding and changes the project's direction; the edit loop every change follows is in the root AGENTS.md. |
| `bootstrap` | [Bootstrapping Checklist](guides/bootstrap.md) | Adopting Irminsul, and the order of the first steps on an existing codebase. |
| `guides` | [Guides](guides/INDEX.md) | How-tos, operating procedures, and the docs about this doc system. |
| `private-docs` | [Private docs for a public code repo](guides/private-docs.md) | Keeping the docs tree private beside an open-source code repo. |
| `release` | [Release Process](guides/release.md) | How a tagged release is built and published. |
| `style-guide` | [Style Guide](guides/style-guide.md) | Authoring conventions for what a sentence earns, when it is a claim, and how an RFC's owner's part reads; a check enforces only an RFC's shape. |

### rfcs

| ID | Doc | Summary |
|----|-----|---------|
| `a-change-re-asks-the-sentences-that-name-its-code` | [A change re-asks the sentences that name its code](rfcs/a-change-re-asks-the-sentences-that-name-its-code.md) | When a change edits code, the review queue asks again about every sentence that names that code in a code span, and `context <path>` lists those sentences before the edit, so an agent finds the docs a change makes stale without searching for them. |
| `a-gate-file-is-sealed-not-scored` | [A gate file is sealed, not scored](rfcs/a-gate-file-is-sealed-not-scored.md) | A changed workflow or action file that mentions irminsul is a certain finding until a decision record names it, replacing gate-strength scoring and the emulation of GitHub path filters. |
| `a-path-is-named-when-git-lists-it` | [A path is named when git lists it](rfcs/a-path-is-named-when-git-lists-it.md) | A path a doc names exists when git lists it or the source walk holds it, not when a file happens to be on one machine's disk, so the same tree gives the same findings everywhere. |
| `a-source-file-has-one-claim` | [A source file has one claim](rfcs/a-source-file-has-one-claim.md) | A source file matched by two docs' describes is a certain error answered by narrowing the broader claim, a doc may exclude files from its own glob, and the specificity tie-break and two overlap hints go. |
| `acknowledge-a-reviewed-co-change-or-evidence-drift` | [Acknowledge a reviewed co-change or evidence drift](rfcs/acknowledge-a-reviewed-co-change-or-evidence-drift.md) |  |
| `an-rfc-has-an-owners-part-and-an-agents-part` | [An RFC has an owner's part and an agent's part](rfcs/an-rfc-has-an-owners-part-and-an-agents-part.md) | Every RFC opens with a short part the owner reads to decide, and keeps the names, ids and migration lists an agent needs in a part after it. |
| `claim-evidence-names-a-part` | [Claim evidence names a part](rfcs/claim-evidence-names-a-part.md) | A claim's evidence may name part of a file, found by a finder its extension selects, so its pin re-asks the claim only when that part changes; anchors resolve through the same finders, and evidence drift is then judged in every layer. |
| `decision-records-govern-what-they-decide` | [Decision records govern what they decide](rfcs/decision-records-govern-what-they-decide.md) | A sign-off for one change becomes a commit trailer, and a decision record becomes a living topic that declares what it governs, is the only record for it, and is edited in place with a dated Changes line when its rule changes. |
| `every-warning-hint-has-an-answer` | [Each finding code has one answer](rfcs/every-warning-hint-has-an-answer.md) | Every finding code declares one answer, a commit trailer is the one acknowledgement step, and the dead ends an audit of all 174 codes found get an answer here or in a separate bug fix, so the gate that fails on hints never fails a correct doc; an accepted RFC's tasks also gain checkboxes, and ticking the last one asks for finalization. |
| `rfcs` | [RFCs](rfcs/INDEX.md) | Proposals moving through the change lifecycle. |

<!-- agents-manifest:generated-end -->

## Foundations

The Three Laws of Maintenance and the principles behind them are in
[`foundation/principles.md`](foundation/principles.md#the-three-laws-of-maintenance).

## Protocol

The edit loop is in the root [`AGENTS.md`](../AGENTS.md); acting on a finding and changing
direction are in [`guides/agent-protocol.md`](guides/agent-protocol.md).
