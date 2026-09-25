# Agent Navigation Manifest

This manifest is the curated entry point into `docs/` for agents. The
documentation-tree table below is generated; the Foundations and Protocol
sections are curated. Run `irminsul regen agents-md` after adding or
moving docs.

New and updated docs should set a one-line `summary:` in their frontmatter
so they describe themselves in the table below; the Summary column appears
automatically once any doc declares one.

## About this manifest

- **Don't hand-edit between the markers.** Anything between
  `agents-manifest:generated-start` and `agents-manifest:generated-end` is
  rewritten by `irminsul regen agents-md`. Edits to the intro, this section,
  Foundations, and Protocol are curated and survive regens.
- **How to read the table.** Rows are grouped by docs-tree layer. Docs that
  live directly under `docs/`, such as a project-wide INDEX, appear under `(root)`. Exempt navigation files — `README.md`, `GLOSSARY.md`,
  `CONTRIBUTING.md`, `CLAUDE.md`, and `AGENTS.md` itself — are intentionally not listed;
  they aren't doc atoms.
- **The Foundations and Protocol sections are yours.** They scaffold with
  Irminsul's default doc-system framing, but downstream projects are meant to
  edit them to their own taste; `irminsul regen agents-md` preserves the
  edits.

## Documentation Tree

<!-- agents-manifest:generated-start -->

### architecture

| ID | Doc | Summary |
|----|-----|---------|
| `architecture` | [Architecture](architecture/INDEX.md) |  |
| `check-pipeline` | [Check Pipeline](architecture/check-pipeline.md) |  |
| `component-hierarchy` | [Component Hierarchy and Doctrine](architecture/component-hierarchy.md) |  |
| `layers` | [Layers](architecture/layers.md) |  |
| `levels-and-views` | [Architecture Levels and Views](architecture/levels-and-views.md) |  |
| `overview` | [Architecture overview](architecture/overview.md) |  |
| `tooling` | [Tooling Stack and Deployment](architecture/tooling.md) |  |

### components

| ID | Doc | Summary |
|----|-----|---------|
| `adoption-record` | [Adoption record](components/adoption-record.md) | The finite list of managed files that had no owning doc when an existing repository adopted Irminsul; it excepts those files from the ownership finding, only shrinks, switches nothing on or off, cannot except a file the base of the diff already documented, and pins the revision of any source repository whose files it names. |
| `anchors` | [Anchored prose claims](components/anchors.md) |  |
| `baseline` | [Baseline ratchet](components/baseline.md) | Brownfield adoption mechanism — a baseline file records existing certain findings so CI fails only on new ones; it is created once, only shrinks, and shows what it hides. |
| `change` | [Change lifecycle](components/change.md) |  |
| `checks` | [Checks](components/checks.md) |  |
| `cli` | [CLI](components/cli.md) |  |
| `components` | [Components](components/INDEX.md) |  |
| `config` | [Config](components/config.md) |  |
| `context` | [Agent context command](components/context.md) | Runtime map of what governs a path — owning doc, recommended tests, dependencies, active RFCs, findings, and next commands — for the start and end of an edit. |
| `doc-atom` | [The Doc Atom Specification](components/doc-atom.md) |  |
| `docgraph` | [DocGraph](components/docgraph.md) | The in-memory model of the docs tree that every check receives — what it holds, what it records instead of raising, how data beyond the docs reaches a check, and the one reader that decides what counts as fenced code. |
| `frontmatter` | [Frontmatter](components/frontmatter.md) |  |
| `git` | [Git helpers](components/git.md) |  |
| `init` | [Init scaffolder](components/init.md) |  |
| `languages` | [Language profiles](components/languages.md) |  |
| `mcp-server` | [MCP server](components/mcp-server.md) | Read-only MCP stdio server that lets AI agents query the doc graph natively instead of shelling out to the CLI. |
| `new-list-regen` | [New / List / Regen / Fix commands](components/new-list-regen.md) |  |
| `orient` | [Agent orientation command](components/orient.md) | The recommended first call for agents — repo structure, doc totals, entry docs, and the command vocabulary as one stable report. |
| `refs` | [Refs backlink and symbol query](components/refs.md) |  |
| `seed` | [Seed command](components/seed.md) |  |
| `status` | [Status command](components/status.md) | One-glance digest of docs inventory, source-file coverage, and findings. |
| `surface` | [Surface extraction & on-demand derivation](components/surface.md) |  |

### decisions

| ID | Doc | Summary |
|----|-----|---------|
| `a-governing-claim-ends-by-decision-not-by-deleting-its-evidence` | [A governing claim ends by decision, not by deleting its evidence](decisions/a-governing-claim-ends-by-decision-not-by-deleting-its-evidence.md) | Removing a claim that governed its evidence at the base of a change is a certain finding even when the evidence is deleted too; only a decision record in the same change ends the contract. |
| `a-snapshot-is-judged-by-its-own-configuration` | [A snapshot is judged by its own configuration](decisions/a-snapshot-is-judged-by-its-own-configuration.md) | Ownership at the merge base is read with the merge base's `irminsul.toml`, so one change cannot alter what the base meant; the governing claim `adoption-exception-does-not-return` says so. |
| `adoption-and-repository-layouts` | [Adoption and repository layouts](decisions/adoption-and-repository-layouts.md) | irminsul init adopts existing code or starts fresh in one of two layouts, same-repo or siblings, and irminsul seed captures initial intent into the foundation layer. |
| `agent-interface` | [Agent interface](decisions/agent-interface.md) | Agents orient, gather context, and query references through read-only commands and an MCP server, guided by a generated manifest, a written work order, and harness wiring scaffolded at adoption. |
| `anchors-bind-code-names-in-any-language` | [Anchors bind code names in any language](decisions/anchors-bind-code-names-in-any-language.md) | A doc binds each code name it cites to the file that defines it with an anchor; Irminsul lists unbound names for review, suggests candidate files, and resolves anchors in any language. |
| `authority-follows-the-kind-of-claim` | [Authority follows the kind of claim](decisions/authority-follows-the-kind-of-claim.md) | Code is authoritative for mechanically reconstructable implementation state and not for intent, constraint, or rationale; a claim declares its relation to the evidence it cites, and that relation decides who wins a disagreement and what changing the claim means. |
| `baseline-holds-certain-findings-and-only-shrinks` | [Baseline holds certain findings and only shrinks](decisions/baseline-holds-certain-findings-and-only-shrinks.md) | The baseline records only certain findings, is created once and afterwards only loses entries, and every run shows people what it hides. |
| `change-lifecycle` | [Change lifecycle](decisions/change-lifecycle.md) | RFCs move through four states bound to repository evidence, implemented records do not change until consolidated into ADRs, and retirements live as tombstones on stable ADRs. |
| `context-keeps-no-session-external-checks-may-cache-observations` | [Context keeps no session; external checks may cache observations](decisions/context-keeps-no-session-external-checks-may-cache-observations.md) | Context stores nothing that a later call reads and re-derives every repository result, while an external-link check may reuse a bounded cache whose results are reported as observations from their recorded time. |
| `decisions` | [Architecture decisions](decisions/INDEX.md) |  |
| `derive-dont-materialize` | [Derive, don't materialize](decisions/derive-dont-materialize.md) | Facts reconstructable from code are derived on demand; docs keep curated intent, which watched and explained surfaces keep honest, and a review queue routes semantic checking to readers. |
| `deterministic-enforcement` | [Deterministic enforcement](decisions/deterministic-enforcement.md) | Every check is deterministic; each finding's class decides whether it blocks, and baselines, deltas, co-change, and fixes shape how findings reach a team. |
| `docs-carry-no-audience-field` | [Docs carry no audience field](decisions/docs-carry-no-audience-field.md) | The required audience frontmatter field is removed; a decision record is known by its layer, and writing for one reader stays a writing rule, not metadata. |
| `documentation-model` | [Documentation model](decisions/documentation-model.md) | Six configurable layers of single-purpose doc atoms with validated frontmatter, folder-owned navigation, per-layer rules, structured ADRs, and an opt-in glossary. |
| `drafts-excuse-an-unfinished-doc-not-a-wrong-one` | [Drafts excuse an unfinished doc, not a wrong one](decisions/drafts-excuse-an-unfinished-doc-not-a-wrong-one.md) | A certain finding is demoted on a draft doc only when its code reports the doc as unfinished; a finding about the doc's relationship to code or to other docs is an error whatever the doc's status. |
| `finding-classes-decide-what-blocks` | [Finding classes decide what blocks](decisions/finding-classes-decide-what-blocks.md) | Every finding code is certain, hint, or time; certain findings block, hints are investigated, time findings stay off pull requests, and one enabled list replaces hard and soft. |
| `git-history-seals-implemented-records` | [Git history seals implemented records](decisions/git-history-seals-implemented-records.md) | An implemented RFC or an accepted decision is immutable because the protected branch's history says so, not because of a hash the author can recompute; frozen_hash is removed. |
| `mark-review-items-by-symbol-freshness` | [Mark review items by symbol freshness](decisions/mark-review-items-by-symbol-freshness.md) | The review queue marks a sentence only when the definition it names changed after the doc, and shows marked sentences by default. |
| `records-are-named-by-slug` | [Records are named by slug](decisions/records-are-named-by-slug.md) | RFCs and decision records are files named by a slug of their title, with no number; order and relationships come from links and git, not from the filename. |
| `removing-a-claim-about-surviving-code-is-a-finding` | [Removing a claim about surviving code is a finding](decisions/removing-a-claim-about-surviving-code-is-a-finding.md) | Deleting an anchor, a claims entry, or an inventory entry is an error when the code it named still exists, and reported not at all when that code went away in the same change. |
| `ship-framework-packs-with-kind-capabilities` | [Ship framework packs with kind capabilities](decisions/ship-framework-packs-with-kind-capabilities.md) | Code surfaces for popular stacks ship as built-in data packs, and checks read a kind's declared capabilities instead of branching on its name. |
| `splitting-a-doc-keeps-one-description` | [Splitting a doc keeps one description of the code](decisions/splitting-a-doc-keeps-one-description.md) | A new component doc cannot take files another doc owns without naming that doc; moved files and unlinked overlapping claims surface as hints and review items. |
| `switching-a-check-off-is-more-than-a-list-edit` | [Switching a check off is more than a list edit](decisions/switching-a-check-off-is-more-than-a-list-edit.md) | The config seal covers the settings that decide how much a check asks, not only the list of checks, and a CI step counts as a gate only if its result can fail the run. |
| `unclaimed-code-in-documented-territory-is-an-error` | [Unclaimed code in documented territory is an error](decisions/unclaimed-code-in-documented-territory-is-an-error.md) | A source file that no doc claims, in a directory that holds documented code or was added inside one, fails the build instead of warning, so documentation cannot quietly stop covering the code it covers. |
| `weakening-the-config-needs-a-decision-record` | [Weakening the config needs a decision record](decisions/weakening-the-config-needs-a-decision-record.md) | Under --diff, turning a check or a layer rule off is certain unless the same change adds a decision record naming it; narrowing what the checks read is a hint. |

### foundation

| ID | Doc | Summary |
|----|-----|---------|
| `anti-patterns` | [Anti-Patterns](foundation/anti-patterns.md) |  |
| `enforcement` | [Mechanical Enforcement](foundation/enforcement.md) | How documentation rules become deterministic checks, which findings block and which advise, and why CI rather than local tooling is where they hold. |
| `foundation` | [Foundation](foundation/INDEX.md) |  |
| `principles` | [Principles](foundation/principles.md) |  |

### guides

| ID | Doc | Summary |
|----|-----|---------|
| `agent-protocol` | [Agent lifecycle protocol](guides/agent-protocol.md) | The required work order any agent must follow when editing this repository. |
| `bootstrap` | [Bootstrapping Checklist](guides/bootstrap.md) |  |
| `guides` | [Guides](guides/INDEX.md) |  |
| `private-docs` | [Private docs for a public code repo](guides/private-docs.md) |  |
| `release` | [Release Process](guides/release.md) |  |
| `style-guide` | [Style Guide](guides/style-guide.md) |  |

### rfcs

| ID | Doc | Summary |
|----|-----|---------|
| `rfcs` | [RFCs](rfcs/INDEX.md) |  |

<!-- agents-manifest:generated-end -->

## Foundations

Read this before editing any doc. Full detail lives in `docs/foundation/`
and `docs/architecture/`.

### The Three Laws of Maintenance

> **Law 1.** Each fact has exactly one home.
>
> **Law 2.** Each document has exactly one purpose and one audience moment.
>
> **Law 3.** Every cross-reference is machine-verifiable and can be followed in both directions.

### The Layers

- `foundation` — principles and non-goals; rarely changes.
- `architecture` — how the parts fit and how data flows between them.
- `components` — one doc per component: the "what".
- `decisions` — ADRs: the "why".
- `rfcs` — proposals moving through the change lifecycle.
- `guides` — how-tos, operations, and the docs about this doc system.

## Protocol

Before editing docs, follow the agent lifecycle protocol: read this
manifest, run `irminsul context <path>` to locate ownership, tests, dependencies,
and findings, create or update RFCs and ADRs for direction or behavior
changes, keep the affected docs current, and run
`irminsul check` before returning work.

The full lifecycle work order lives at
[`guides/agent-protocol`](guides/agent-protocol.md).
