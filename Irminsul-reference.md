# A Documentation System for Complex Codebases

> A reference architecture for project documentation that generalizes across domains. Designed to resist rot, scale with complexity, and survive philosophy shifts.

---

## Part I — Why Documentation Rots (And Why Structure Alone Won't Save You)

Most documentation systems fail not because people are lazy, but because the system makes the right action harder than the wrong one. When updating a doc requires editing three files in three folders, none of which are obviously canonical, people skip it. When a fact is duplicated across five places, even disciplined contributors update three of them. The rot is structural, not moral.

A working documentation system has three properties:

1. **A single home for every fact** — there is exactly one place where any given piece of information lives. Everywhere else, that information is referenced or transcluded.
2. **An obvious destination for every new piece of writing** — when you have something to document, the system tells you where it goes without ambiguity.
3. **Mechanical enforcement of its own rules** — humans don't police the system; CI does.

The rest of this document defines that system.

---

## Part II — Five Core Principles

### 1. Single Source of Truth (SSOT)
Every fact has exactly one canonical home. All other appearances are references to that home, not copies of it. If you find yourself typing the same definition twice, you've created a future contradiction.

### 2. Provenance
Every non-trivial claim in the docs must trace back to one of three sources: **the source code**, **an Architecture Decision Record (ADR)**, or **an external citation**. Floating assertions ("we use eventual consistency because it's simpler") are forbidden — either point to the ADR that decided it, or write that ADR.

### 3. Audience Separation
Every document is written for one reader in one mental state. The Diataxis framework names four such moments: *learning* (tutorial), *doing* (how-to), *understanding* (explanation), *referring* (reference). A doc that tries to serve two of these serves neither.

### 4. Code as Ultimate Truth
When code and docs disagree, code wins by default. This means anything that *can* be generated from code *should* be — schemas, type signatures, API surfaces, config references, error catalogs. Hand-written docs cover only what code cannot express: intent, trade-offs, and process.

### 5. The Doc Graph is Bidirectional
If `composer.md` references `data-model.md`, then `data-model.md` should automatically show "referenced by composer.md" at the bottom. Backlinks are generated, not maintained. This makes "what breaks if I change this?" a one-glance question.

---

## Part III — The Three Laws of Maintenance

These are the operational consequences of the principles above. They are simple enough to enforce mechanically.

> **Law 1.** Each fact has exactly one home.
>
> **Law 2.** Each document has exactly one purpose and one audience moment.
>
> **Law 3.** Every cross-reference is bidirectional and machine-verifiable.

When something feels wrong with a doc, ask which law it's violating. The answer almost always points at the fix.

---

## Part IV — The Doc Atom

A "doc atom" is the smallest unit of documentation that has a single purpose. Every doc in the system is an atom, defined by required frontmatter:

```yaml
---
id: composer
title: Composer Component
audience: explanation       # tutorial | howto | reference | explanation
tier: 2                     # see tier system below
status: stable              # draft | stable | deprecated
owner: @anson               # CODEOWNERS handle
last_reviewed: 2026-05-07
describes:                  # source files this doc claims to describe
  - app/composer/*.py
  - app/prompts/composer/*
depends_on:                 # other docs this one references
  - reference/program-schema
  - reference/data-model
supersedes: []              # older docs this replaces
---
```

This frontmatter is the contract. CI reads it to enforce ownership, detect drift (`describes` files newer than the doc), generate backlinks (from `depends_on`), inject status banners, and route review reminders.

### The Tier System

Not every doc deserves the same treatment. Classify each by how it's maintained:

| Tier | Name | Edited By | Review Cadence | Examples |
|------|------|-----------|----------------|----------|
| T1 | Generated | CI only | Never | API reference, type schemas, config reference |
| T2 | Stable | Humans, rarely | On structural change | Principles, architecture overview, ADRs |
| T3 | Living | Humans, often | Quarterly | Component docs, workflows, runbooks |
| T4 | Ephemeral | Anyone | Discarded after use | Sprint plans, RFCs in flight |

Tier dictates enforcement: T1 docs are in `.gitignore` and rebuilt every PR; T3 docs trigger drift warnings if their `describes` files change without them; T4 docs auto-archive after a deadline.

---

## Part V — The Layered Directory Structure

```
/docs
├── README.md                      # Map of the system
├── GLOSSARY.md                    # Canonical vocabulary (the dictionary)
├── CONTRIBUTING.md                # How to write docs in this system
│
├── 00-foundation/                 # Things that rarely change (T2)
│   ├── principles.md              # Goals, non-goals, design philosophy
│   ├── constraints.md             # Technical, business, ethical limits
│   └── stakeholders.md            # Who this exists for
│
├── 10-architecture/               # The "what" (T2)
│   ├── overview.md                # C4 Level 1: System Context
│   ├── containers.md              # C4 Level 2: Containers (services, DBs, queues)
│   ├── boundaries.md              # Trust zones, security boundaries
│   └── deployment.md              # Topology, environments, regions
│
├── 20-components/                 # The "what" at component level (T3)
│   ├── INDEX.md                   # Auto-generated from frontmatter
│   ├── composer.md                # Simple component: single file
│   ├── interpreter.md
│   └── planner/                   # Complex component: folder
│       ├── INDEX.md               # L3 entry, broad describes
│       ├── routing.md             # Narrower describes
│       └── caching.md
│
├── 30-workflows/                  # Cross-component "how" (T3)
│   ├── INDEX.md
│   ├── generation-pipeline.md
│   ├── auth-flow.md
│   └── ...
│
├── 40-reference/                  # Generated. Do not edit by hand. (T1)
│   ├── api/                       # OpenAPI-rendered or auto-extracted
│   ├── schema/                    # Pydantic/Zod/Proto → Markdown
│   ├── config/                    # Settings reference
│   ├── events/                    # Event catalog
│   └── errors/                    # Error code dictionary
│
├── 50-decisions/                  # The "why" (T2, append-only)
│   ├── INDEX.md
│   ├── 0001-monorepo-vs-polyrepo.md
│   ├── 0002-pydantic-not-dsl.md
│   └── ...
│
├── 60-operations/                 # Run the thing (T3)
│   ├── runbooks/                  # Step-by-step for known incidents
│   ├── playbooks/                 # Recurring ops procedures
│   ├── slos.md                    # Service-level objectives
│   ├── observability.md           # Metrics, logs, traces strategy
│   └── oncall.md
│
├── 70-knowledge/                  # Audience-facing learning (T3)
│   ├── tutorials/                 # Learning-oriented (Diataxis)
│   ├── howtos/                    # Task-oriented (Diataxis)
│   └── explanations/              # Understanding-oriented (Diataxis)
│
├── 80-evolution/                  # Where the system is going (T4 mostly)
│   ├── roadmap.md
│   ├── rfcs/                      # Proposals before decisions
│   ├── risks.md                   # Risk register
│   ├── debt.md                    # Tech debt registry
│   └── deprecations.md            # What's going away and when
│
└── 90-meta/                       # Docs about docs
    ├── doc-system.md              # This file
    ├── style-guide.md
    └── health-dashboard.md        # Auto-generated metrics
```

The numeric prefixes serve two purposes: stable sort order for humans browsing the tree, and namespacing so doc IDs can use bare slugs (`composer` rather than `components/composer`).

---

## Part VI — Architecture: Levels and Views

The `10-architecture/` folder hybridizes two architectural-doc traditions: the C4 zoom levels (Simon Brown) for logical structure, and the 4+1 view model (Kruchten) for cross-cutting concerns that don't fit a single zoom level.

### Levels (Logical Zoom)

- **Level 1 — System Context.** Your system as a single box: users, external systems, boundaries of responsibility. `10-architecture/overview.md`. Audience: anyone, including non-technical.
- **Level 2 — Containers.** Deployable units (web app, API, worker, DB, queue). `10-architecture/containers.md`. Audience: any engineer.
- **Level 3 — Components.** What lives inside each container. **The entire `20-components/` folder is L3.** No separate L3 file under architecture.
- **Level 4 — Code.** Omitted. Class and sequence diagrams either generate themselves from code or aren't worth the maintenance.

L1 and L2 are hand-drawn (Mermaid, source-controlled). L3's index page generates automatically from the frontmatter of each component doc.

### Views (Cross-Cutting Concerns)

Levels are about *zoom*. Views are about *concern* — different lenses on the same architecture. They are not levels; they overlay on L1 and L2.

- **Deployment view.** Where things run: regions, environments, replication, scaling. `10-architecture/deployment.md`. Overlays on L2.
- **Security view.** Trust zones, authentication boundaries, data classification. `10-architecture/boundaries.md`. Overlays on L1 and L2.
- **Data view** (optional). Where data lives, how it flows, retention policy. Useful when data shape dominates design.

This adapts Kruchten's 4+1 view model. The C4 levels are the logical view; deployment and security are alternate views of the same architecture under different concerns. The framing matters because it answers "where does deployment go?" without forcing it into a zoom level it doesn't belong to.

### Single File by Default; Folder Only When Needed

A component is a single `.md` file by default. **The hierarchical structure (folder with INDEX.md plus children) is the exception, not the rule.** It applies only when one file becomes unreadable — rule of thumb: >~500 lines, or covering multiple subsystems each with their own design narrative.

Most components in most codebases stay single-file forever. For those, none of the parent-child machinery in the next subsection (doctrine, mtime cascade, children registry, contradiction detector) applies at all. The single file owns its `describes` claim, runs through normal staleness checks, and that's it.

The system warns when a doc exceeds an extreme length (~800 lines) but never forces the split. Promotion to a folder is a human judgment call, made when one file genuinely doesn't fit anymore:

```
20-components/
├── composer.md                # Simple: single file
├── interpreter.md
└── planner/                   # Complex: folder
    ├── INDEX.md               # L3 entry, broad describes
    ├── routing.md             # Subsystem doc, narrower describes
    ├── caching.md
    └── error-handling.md
```

The INDEX.md is the L3 entry — it appears in the components index, holds the broad `describes` claim, and gives the architectural overview. Children describe slices that warrant their own narrative.

### Hierarchical Describes (Specificity Rule)

When components are folders, the coverage-uniqueness rule (Part VIII) extends to handle nesting: **exactly one *most-specific* doc claims each source file.** A child doc claiming `app/planner/routing/*.py` shadows the parent's claim of `app/planner/*.py` for exactly those files. The parent retains authority over everything not shadowed.

This pattern matches `.gitignore` and CSS specificity — the most-specific match wins. CI builds the claim graph at validation time and resolves shadowing before the uniqueness check runs. From the rule's perspective every source file still has exactly one canonical doc; specificity just picks which one.

### Parent-Child Consistency in Component Folders

**This subsection only applies when a component is a folder.** Single-file components have no parent-child concern.

Hierarchical describes solves *file* coverage. It does not solve *fact* consistency: a parent INDEX.md and its children can both be currently aligned with their source paths while saying contradictory things about overlapping concerns. Mtime drift won't catch this.

#### The Doctrine (Primary Principle)

Parents and children must never document the same *kind* of fact. The folder INDEX.md owns *architecture, integration, intent, contracts* — what the component is, what it exposes, how it fits into the larger system. Children own *implementation* — algorithms, data structures, edge cases.

Same principle as good code design: parent modules expose interfaces, children implement specifics. `planner/INDEX.md` should say "the planner orchestrates routing, caching, and error handling to produce a Plan from a request, with contract `(Request) → Plan | PlanError`." It should NOT say "uses Gemini 2.5 Flash with a 30s timeout" — that's a routing concern, owned by `routing.md`. If a fact could legitimately go in either, it goes in the child by default.

Without doctrine, no mechanical check rescues this — every parent accumulates child-level facts that drift, and contradiction becomes inevitable. With doctrine, contradiction becomes structurally rare.

#### Mechanical Enforcement of the Doctrine

Several checks make the highest-frequency doctrine violations costly and visible. These are deterministic and build-blocking unless noted:

1. **Schema/code-leak detection in parent INDEX.md.** The schema-leak rule from Part VIII applies extra strictly to parent docs: regex bans on class definitions, type signatures, specific library-version strings, and substantive code blocks. These belong in children.
2. **No-broad-globs in parents-with-children.** If a folder has children, its INDEX.md's `describes` field must be empty or an explicit list of files — never directory wildcards. Forces the parent to declare exactly what it owns versus what it delegates to children. Build fails on broad globs in parent docs.
3. **Length cap as smell.** Warn if an INDEX.md exceeds ~300 lines. Architecture writing should be concise; long parents indicate accumulated implementation detail. Advisory.
4. **Children registry consistency.** The folder's INDEX.md declares `children: [routing, caching, error-handling]` in frontmatter. CI verifies this matches the folder contents on disk. Adding or removing a child without updating the registry fails the build — forces an explicit decision about whether the parent narrative needs to acknowledge the change.
5. **Mtime cascade.** A parent's *effective* mtime is `max(own_mtime, max(child_mtimes))`. When any child is edited substantively, the parent's effective mtime updates and the staleness check re-evaluates against the parent's `last_reviewed` field. If the parent hasn't been reviewed since a child was rewritten, the renderer injects a `[CHILD-DRIFT]` badge. Advisory, not blocking.
6. **LLM contradiction detector (advisory).** Nightly job reads each parent together with all its children and asks the model to flag direct contradictions. Catches cases where two prose statements happen to disagree (parent says "synchronous flow," child says "events queue for async processing"). Opens an issue, never blocks.
7. **LLM scope-appropriateness check (advisory).** Reads each parent and flags paragraphs that look like implementation detail rather than architecture/integration. Opens an issue, never blocks.

#### The Honest Limit

The semantic boundary between "architectural" and "implementational" cannot be fully mechanized. Two reviewers can legitimately disagree about which side a paragraph falls on. No regex catches "this is too detailed for a parent doc."

The deterministic checks (1–5) reduce the surface area where doctrine can be violated. The LLM advisory checks (6, 7) catch a fraction of the residual semantic cases. Everything else is review quality — every PR touching an INDEX.md should be reviewed by someone who understands the doctrine, and the children-registry rule (4) guarantees such PRs always exist when structure changes.

The principle: when a check cannot be mechanized, the next best thing is to make violations costly, easy to spot in review, and rare. Doctrine clears those bars. It is not magically self-policing.



Because L3 components are real files on disk, the system can mechanically detect when component docs go stale. CI runs three checks on every PR:

1. **Glob resolution.** Every path glob in any doc's `describes` field must match at least one file in the repo. If a source file is renamed or deleted and the doc isn't updated, the glob resolves to zero files and CI fails: *"composer.md describes `app/composer/*.py` but no such files exist. Update or delete the doc."*

2. **Coverage uniqueness (with specificity).** Every source file under a doc-covered directory must be claimed by *exactly one most-specific* doc's `describes`. Two docs claiming the same files at the same specificity fails the build (silent duplication). Zero docs claiming a file in a covered directory warns (silent omission — you added code without a doc).

3. **Mtime drift.** For every T3 component doc, compare last-commit time of the doc vs. last-commit time of any file matching its `describes` globs. If source is newer by more than N commits or D days, CI emits a warning and the renderer injects a `[STALE]` badge on the doc until someone reconciles them.

The first two are hard build-blocking checks. The third is advisory.

---

## Part VII — Cross-Cutting Mechanisms

### The Glossary

A single `GLOSSARY.md` is the authoritative dictionary for all domain terms. Its job is to kill the silent failure mode where "Plan," "Program," and "Recipe" each accumulate three subtly different definitions across the codebase.

Each entry has:

- **Term** (singular, capitalized).
- **Definition** in one or two sentences.
- **Aliases** — informal synonyms used in the codebase ("a Step is sometimes called an Action").
- **Negative space** — what the term is NOT, when ambiguity exists ("Skill is not a Recipe; a Skill is reusable across Recipes").
- **Bounded context** — if the same word means different things in different parts of the system, scope it. ("Recipe (user-facing): the JSON the API returns. Recipe (execution): the deserialized Pydantic object the worker runs.") This is the documentation analog of DDD's bounded contexts.
- **Since** — the version or PR where the term was introduced. Helps when reading old docs.

CI enforces: any capitalized noun phrase used three or more times across the docs must have a glossary entry, OR be on the **anti-glossary** — a list of explicitly banned synonyms ("Don't say `Workflow`; we call it `Pipeline`"). The anti-glossary is as important as the glossary itself, because new contributors will otherwise politely introduce parallel vocabulary that nobody catches in review.

### Architecture Decision Records (ADRs)

ADRs are the canonical home for *why*. Use the standard template (Michael Nygard's original works fine):

```
# ADR 0042: Adopt event sourcing for the order service

## Status
Accepted, 2026-04-01. Supersedes ADR-0019.

## Context
What forces are at play? What are we currently doing?

## Decision
What we will do.

## Alternatives Considered
What we explicitly rejected, and why.

## Consequences
What becomes easier. What becomes harder. What new risks appear.
```

Two non-obvious rules:
- **ADRs are append-only.** Never edit a past ADR's decision. If it changes, write a new one and mark the old as `Superseded by ADR-XXXX`.
- **The "Alternatives Considered" section is mandatory.** Without it, future contributors will keep proposing the same rejected ideas.

### Requests for Comments (RFCs)

RFCs are *proposals before decisions*. They live in `80-evolution/rfcs/` while in flight. The lifecycle:

- **Draft** — author iterates privately or with a small group.
- **Open** — opened for comment. PR comments work; for larger changes use a dedicated discussion thread.
- **Final Comment Period** — explicit "last call" window of N days. Changes during FCP are minor only.
- **Resolved** — Accepted (converts to ADR; RFC marked with the ADR number), Rejected (stays with `Status: Rejected` and reasoning), or Withdrawn.

Two requirements that prevent RFCs from festering:

- **Decision Owner.** One person is named in the RFC frontmatter as accountable for driving it to resolution. Without an owner, RFCs sit open for months.
- **Target Decision Date.** Set at draft time. CI auto-pings the Decision Owner if the date passes without resolution, and after a grace period auto-marks the RFC `Status: Stalled`.

When an RFC becomes an ADR, both link to each other. The RFC stays in `80-evolution/rfcs/` for archival; the ADR is the canonical record going forward.

### Runbooks

Runbooks live in `60-operations/runbooks/` and exist for one purpose: to be useful at 3am when an alert fires. Optimize aggressively for that moment.

Structure (same skeleton for every runbook, no exceptions):

1. **Symptom** — the exact alert text or observable behavior. This is the search target. Runbook IDs should match alert IDs in your monitoring system, so the alert page links directly to the runbook.
2. **Quick Mitigation** — the dumbest thing that often works. Restart, scale up, fail over. This is what a tired on-call engineer does first.
3. **Diagnosis Tree** — branching checks: "if X is high, then Y; if Z is timing out, then W."
4. **Root Cause Investigation** — once stable, the deeper analysis steps.
5. **What NOT to Do** — common mistakes that worsen the incident. Critically important and almost always omitted from runbooks. This is often the most valuable section.
6. **Postmortem Template Link** — direct link to the postmortem doc to fill out after.

Two staleness defenses specific to runbooks:

- **Last Validated.** Frontmatter field updated whenever on-call confirms the runbook actually worked. CI flags runbooks not validated in 6 months.
- **Game Days.** Scheduled exercises where the team manually triggers a scenario in non-prod and runs the runbook end-to-end. Catches drift no static check can.

### Backlinks

Generated at compile time by walking the link AST. Every doc gets an auto-injected "Referenced by" section listing all docs that link to it.

Two refinements that matter:

- **Strong vs weak links.** A weak link is any prose mention. A strong link is a `depends_on` frontmatter entry — it declares "if this referenced doc changes, this doc must be reviewed." Strong links are the impact graph; weak links are search context. Render them as separate sections at the bottom of each doc.
- **Deprecation propagation.** When a doc is marked `status: deprecated`, every doc that strong-links to it gets flagged. The renderer injects a warning banner at the top of those docs: *"This doc has strong dependencies on deprecated components: [list]."* This makes it impossible for a stable workflow doc to quietly depend on a deprecated component without anyone noticing.

The "what breaks if I change this?" question becomes: pull all strong backlinks of the doc you're touching. That's the review set.

---

## Part VIII — Mechanical Enforcement

The point of the whole system is that you don't have to remember the rules. CI does.

### Two Tiers of Enforcement

Every check in this system falls into one of three categories:

- **Hard (deterministic, blocking).** Fail the PR. Enforce structural invariants.
- **Soft, deterministic (advisory).** Warn, badge, or open an issue. Detect drift.
- **Soft, LLM-based (advisory only).** Open an issue, never block. Catch semantic cases structural checks miss.

The boundary between hard and soft is principled: **build correctness never depends on LLM judgment.** A hallucinated finding should never prevent a merge. Hard checks are pure graph operations, set comparisons, regex, glob resolution, and git-log arithmetic — fully deterministic.

| Tier | Examples |
|------|----------|
| Hard | Frontmatter validity, glob resolution, coverage uniqueness, internal link integrity, schema-leak detection, supersession auto-update, forced reckoning on source deletion |
| Soft, deterministic | Mtime drift, external link rot, stale-doc reaper, orphan detector, ADR-touching policy reminder, Change Triplet declaration check |
| Soft, LLM | Behavioral overlap detector, semantic drift judge |

Hard checks together guarantee no PR can merge while violating the structural invariants. LLM checks exist purely to catch the residual cases — semantic duplication of purpose, prose-vs-code mismatches — and they only ever surface findings for human review.

### The Change Triplet
Every PR must touch some combination of three things: **code**, **tests**, **docs**. The PR template asks the author to declare which categories the change affects, and Danger.js (or equivalent) checks the file diff matches the declaration. Pure code changes without doc updates are flagged for justification.

### Pre-commit Hooks (run locally before push)
- Frontmatter validator (required fields present, enums valid)
- Markdown linter (style, broken syntax)
- Internal link checker (no broken `[link](other.md)`)
- Glossary linter (capitalized terms have glossary entries)
- Schema-in-component-doc detector (no SQL/Pydantic class definitions in `20-components/`)

### CI Pipeline (run on every PR)
- All pre-commit checks, plus:
- External link checker (URLs return 2xx or 3xx)
- Reference layer regeneration (T1 docs rebuilt; if the rebuild changes the output, the PR's doc preview shows the diff)
- Drift detector (for each T3 doc, compare last-commit time of `describes` files vs. the doc; warn if source is N commits or D days newer)
- Doctest runner (executable code blocks tagged `python {test}` are extracted and run)
- Orphan detector (docs with no inbound links and not in any INDEX)
- ADR-touching detector (if the PR modifies core schemas or migrations and no new ADR appears, leave a comment)
- LLM judge (advisory only — small model checks each modified component doc against its source files and opens an issue if they semantically disagree)

### Supersession Enforcement (the "Did Anyone Mark This Deprecated?" Problem)

The most insidious failure mode is silent replacement: someone writes `composer-v2.md` covering the same ground as `composer.md`, but forgets to mark the old doc deprecated. Now both exist, both look authoritative, and they slowly contradict each other. No single rule prevents this — the system uses six layered mechanisms that together make silent rot mechanically very hard:

1. **Coverage uniqueness** (from Part VI). Two docs cannot claim the same source paths in their `describes` fields. If `composer-v2.md` declares `describes: [app/composer/*.py]` and `composer.md` already does, CI fails. The author has three legal options: scope the new doc differently, mark the old doc deprecated (which clears its describes claim), or delete the old doc.

2. **Supersession auto-update.** When a new doc declares `supersedes: [doc-X]` in its frontmatter, CI automatically rewrites doc-X's frontmatter to set `superseded_by: <new-doc>` and `status: deprecated`. The author cannot forget — the act of declaring supersession does the marking.

3. **Forced reckoning on source deletion.** When a PR deletes source files, CI finds every doc whose `describes` field matches those files. The PR is blocked until those docs either (a) update `describes` to drop the deleted paths, (b) are themselves deleted, or (c) get `status: deprecated` with a `superseded_by` link. The author cannot merge a code deletion without explicitly resolving the doc fate.

4. **Banner injection on incoming strong links.** When a doc is marked deprecated, every doc with `depends_on: [deprecated-doc]` gets an automatic warning banner in its rendered output. Stale workflows pointing at deprecated components become visually obvious to the next reader, who will fix the reference or re-evaluate the workflow.

5. **Behavioral overlap detector (advisory).** A nightly LLM judge reads all stable docs and flags pairs that appear to describe the same component or process semantically, even when they don't share `describes` paths. Opens an issue rather than blocking — meant to catch the case where two docs cover the same conceptual ground without overlapping in the structural checks.

6. **Substantive-edit tracking.** Every doc carries a derived `last_substantive_edit` timestamp computed from git history (ignoring whitespace, frontmatter-only, and link-only changes). If a doc's substantive content hasn't changed in 12 months but its `describes` files have churned significantly, the doc is auto-flagged for review.

The combination is the point. Deleting a component forces doc resolution (3). Replacing a component forces supersession, which auto-deprecates the old (1, 2). Deprecating a component visibly poisons every dependent doc (4). And the LLM judge catches the conceptual-overlap case the structural checks miss (5). No single check is bulletproof; the layering is what makes silent contradiction nearly impossible.


- Stale doc reaper (docs with `last_reviewed` older than 90 days get an auto-issue assigned to their owner)
- Health dashboard regeneration (see below)
- Broken external link sweep (catches link rot the PR check missed)

### The Health Dashboard
Auto-generated daily into `90-meta/health-dashboard.md`. Tracks:

- **Coverage:** % of source files that appear in some doc's `describes` field
- **Ownership:** % of docs with a valid CODEOWNER
- **Freshness:** distribution of days-since-last-reviewed
- **Drift:** count of T3 docs where source is newer than doc
- **Orphans:** docs not referenced anywhere
- **Glossary compliance:** undefined capitalized terms by frequency
- **ADR ratio:** ADRs per 100 schema/migration changes (low ratio means decisions aren't being recorded)

These metrics make doc health visible and trackable. What gets measured gets maintained.

---

## Part IX — Evolution Patterns

The system is designed to absorb change without rewrites. Here are the recipes.

### Adding a New Feature
1. Open an RFC in `80-evolution/rfcs/`. Get feedback.
2. On acceptance: convert to ADR in `50-decisions/`, mark RFC `Accepted → see ADR-XXXX`.
3. Implement: code + tests + relevant doc updates in one PR.
4. New components get new files in `20-components/`. New cross-cutting flows get files in `30-workflows/`. The reference layer regenerates itself.
5. If new domain terms appear, add them to `GLOSSARY.md` in the same PR.

### Changing Philosophy (the hardest case)
Philosophy changes — switching from REST to event-driven, from monolith to services, from optimistic to pessimistic concurrency — touch many docs. The system handles this via:

- **One ADR captures the decision** (e.g., "ADR-0078: Move to event-driven architecture")
- **`00-foundation/principles.md` is updated** with a brief note pointing to the ADR
- **Affected component docs are updated** with explicit "Previously: X. Now: Y. See ADR-0078." callouts
- **Old workflow docs are not deleted** — they're marked `status: deprecated` and remain searchable, with a banner pointing to the replacement

The point: philosophy changes leave a clear trail. A new contributor reading `principles.md` sees the current philosophy and the link to the ADR explaining why it changed.

### Deprecating a Component
1. New ADR explaining the deprecation and replacement.
2. Set `status: deprecated` on the component doc.
3. CI auto-injects a deprecation banner with timeline and migration guide link.
4. Add to `80-evolution/deprecations.md` with target removal date.
5. On removal: delete the component, but keep the doc for one full release cycle marked `status: removed`.

### Splitting an Overgrown Doc
When a doc exceeds ~500 lines or its `depends_on` field grows beyond ~8 entries, split it. Keep the original ID as a hub doc that links to the new pieces. CI's drift and link checks will catch any references that broke.

### Merging Redundant Docs
If two docs cover overlapping ground (which the duplication detector should catch), pick a canonical one, redirect the other via `supersedes`, and let the link rewriter update inbound references in a follow-up PR.

---

## Part X — Anti-Patterns

These are the failure modes the system exists to prevent. Naming them helps you spot them in code review.

- **The Mega-README.** A single 4,000-line README that documents everything. Dies because nobody reads past the install instructions, and updates fight for the same lines.
- **The Wiki Graveyard.** Docs in a separate Confluence/Notion that drift independently of code. Defeats the Change Triplet by making doc updates a separate workflow.
- **Duplication-by-Paraphrase.** Same fact stated three different ways across three docs, none of them clearly canonical. Worse than verbatim duplication because diff tools can't catch it.
- **The Tribal Slack.** Critical decisions made in DMs and Slack threads, never written into ADRs. Six months later nobody remembers why.
- **Doc-as-Changelog.** Component docs that read "We used to do X, then we tried Y, now we do Z." They should describe present reality only. History lives in ADRs and git log.
- **The Phantom Owner.** Docs with no `owner` field, or with an owner who left the org. CI should fail PRs that introduce these.
- **Architecture-Astronaut Diagrams.** A single diagram trying to show everything, which ends up showing nothing. C4 levels exist to prevent this — pick a zoom level and stop.
- **Schema Sprawl.** Type definitions appearing in three docs. T1 generation prevents this categorically.
- **The Inscrutable Acronym.** Domain acronyms used everywhere with no glossary entry. The glossary linter catches this.

---

## Part XI — Tooling Stack (Suggested)

Concrete recommendations as of 2026. None of these are load-bearing — substitute equivalents freely.

- **Renderer:** MkDocs with the Material theme, or Docusaurus. Both support frontmatter, plugins, and produce static sites.
- **Diagrams:** Mermaid for everything that fits its grammar (sequence, flowchart, ER, state). PlantUML or Excalidraw for the rest. Always source-controlled, never image-only.
- **API reference:** OpenAPI generated from code, rendered with Redoc or Swagger UI.
- **Schema reference:** `mkdocstrings` (Python), `typedoc` (TS), `protoc-gen-doc` (Protobuf), or hand-rolled scripts.
- **ADR management:** `adr-tools` CLI or `log4brains`.
- **Linting:** `markdownlint` for syntax, `Vale` for prose style.
- **Link checking:** `lychee` (fast Rust-based) for both internal and external.
- **Pre-commit:** the `pre-commit` framework, with hooks pinned by hash.
- **CI:** GitHub Actions, with `Danger.js` for PR-time policy enforcement.
- **Spell/grammar:** `cspell` with a project dictionary that the glossary feeds.
- **LLM judge:** any cheap model with structured output. Treat as advisory, never blocking.

---

## Part XII — Packaging the System for Reuse

The doc system itself — validators, drift detectors, renderer config, ADR templates, frontmatter schema, CI workflows — is codebase-agnostic. It should live in its own repository and be consumed by codebases as a dependency, never copy-pasted into each one. The actual *docs* must live with the code; the *tooling* should not.

### The Distinction That Matters

| Lives in dedicated tooling repo | Lives in each codebase |
|---|---|
| Frontmatter schema definition | Actual frontmatter in each doc |
| Glob / coverage / uniqueness checkers | Doc files claiming source paths |
| Renderer config (MkDocs, Docusaurus) | The `/docs` folder content |
| Diátaxis layer skeleton | Codebase-specific glossary |
| ADR / RFC templates | Actual ADRs and RFCs |
| GitHub Actions workflow definitions | `doc-system.toml` config |
| Pre-commit hook definitions | Repo-specific overrides |
| LLM judge prompts | The codebase's source code |

### Why Co-Location of Docs Is Non-Negotiable

The Change Triplet (code + tests + docs in one PR) requires single-repo atomicity. If docs live in a separate repo, every code change becomes two PRs across two repos with manual coordination — they will desynchronize within weeks. Drift detection by mtime requires single git history. Coverage checks (every source file claimed by some doc) require trivial filesystem access to source. None of this works across repo boundaries without painful sync infrastructure that breaks more often than it works.

### Why Centralization of Tooling Is the Multiplier

The tooling has zero dependency on any specific codebase. Centralizing it gives you one place to fix a bug, one place to add a check, one place to roll out a new convention to every codebase that uses the system. New checks reach all consumers via dependency upgrade. The mental model is the same as testing: pytest is a package, your tests live in your repo. ESLint is a package, your config and code live in your repo. The doc system is the same shape — tool as package, content co-located.

### Shape of the Package

Whatever your ecosystem favors:

- **Python:** `pip install doc-system` — exposes a CLI (`doc-check`, `doc-render`, `doc-init`) and importable validators.
- **Node:** `npm install -D doc-system` — same shape.
- **Polyglot:** a composite GitHub Action published from the tooling repo, callable from any language's CI.

Each consuming codebase has a single config file at root (`doc-system.toml`) declaring its specifics:

```toml
[paths]
docs_root = "docs"
source_roots = ["app", "lib"]

[tiers]
generated = ["docs/40-reference/**"]
stable = ["docs/00-foundation/**", "docs/10-architecture/**", "docs/50-decisions/**"]

[checks]
hard = ["frontmatter", "globs", "uniqueness", "links", "schema-leak", "supersession"]
soft_deterministic = ["mtime-drift", "stale-reaper", "orphans"]
soft_llm = ["overlap", "semantic-drift"]

[overrides]
# Legitimate exceptions, must be commented
ignore_uniqueness = []
mtime_drift_days = 30

[llm]
provider = "anthropic"
model = "claude-haiku-4-5"
```

The tool reads this config, runs the configured checks, and exits with appropriate status codes for CI. Codebases get standardization for free; the tooling repo gets one canonical home for improvements.

### Visibility: All-Private Is the Default

Most projects keep all docs private. **If your code is also private** (the typical company codebase), this is trivial — single repo, every check works as designed, no special handling. Stop reading this subsection.

The only non-trivial case is **code public + docs private**: docs live in their own private repo; code in a public repo; the doc-system tool runs only against the private docs repo. The Change Triplet works inside the private docs repo for internal contributors; external contributors submit code-only PRs and an internal reviewer updates docs as part of merge.

**What this costs you when code is public but docs aren't:**

1. **External contribution context.** Outsiders read your code but not your conventions, ADRs, or design intent. Their PRs are likelier to violate invariants they can't see — you reject more, accept lower-quality, or carry heavier maintainer review burden.
2. **Public-facing documentation.** Users of your library or API have no architecture overview, no contributing guide, no glossary. They reverse-engineer from code. Adoption friction.
3. **Change Triplet for outsiders.** External PRs can't update docs they can't read. Internal reviewers update private docs as part of merge.
4. **Self-documentation pressure.** Writing for strangers forces clarity. All-private docs lose that constraint and tend to drift toward insider jargon over time.

**What you don't give up:** every enforcement check still works identically inside the private docs repo. Internal team experience is the same or better.

#### Decision Table

| Code | Docs | Setup | When to pick |
|------|------|-------|--------------|
| Private | Private | Single repo | Company codebase. Default. |
| Public | Private | Two repos, all-private docs | Public code where API stability > community participation |
| Public | Public | Single repo | Pure community OSS |

Pick the simplest option your project can tolerate. Most should pick row 1.

### Adopting on a New Codebase

Once the tooling repo exists, adopting it on a new codebase is roughly:

1. Add the tool as a dev dependency.
2. Run `doc-system init` — generates `/docs` skeleton, `doc-system.toml`, GitHub Actions workflow, and pre-commit hooks.
3. Write `00-foundation/principles.md` and `10-architecture/overview.md`.
4. Commit. CI now enforces the system from PR #1.

This is the deployment model that lets the doc system itself evolve without forking. Improvements to the tooling propagate via dependency upgrades; the doc content stays anchored to the codebase it describes.

---

## Part XIII — Bootstrapping Checklist

To adopt this system on a new or existing codebase, in order:

- [ ] Create the `/docs` directory tree from Part V
- [ ] Write `00-foundation/principles.md` (even just a paragraph)
- [ ] Write `10-architecture/overview.md` with a C4 L1 diagram
- [ ] Set up `GLOSSARY.md` with whatever terms come to mind first
- [ ] Pick a renderer (MkDocs Material is the lowest-friction default)
- [ ] Add the frontmatter validator as a pre-commit hook
- [ ] Add the link checker to CI
- [ ] Set up `adr-tools` and write ADR-0001 capturing the decision to use this system
- [ ] Add CODEOWNERS coverage for the docs directory
- [ ] Wire up reference-layer auto-generation for at least one schema
- [ ] Add the Change Triplet check to PR template
- [ ] Generate the first health dashboard

You can stop after the first three steps and still be ahead of 90% of codebases. The rest is incremental hardening.

---

## Appendix A — The Audience Moment Test

When you're not sure where a piece of writing belongs, ask: *who reads this, in what state of mind, with what goal?*

| Reader is... | Goal is... | Doc type | Folder |
|--------------|-----------|----------|--------|
| New to the system | "Teach me by doing" | Tutorial | `70-knowledge/tutorials/` |
| Knows the system | "I need to do X right now" | How-to | `70-knowledge/howtos/` |
| Building something nearby | "How does this work conceptually?" | Explanation | `20-components/` or `70-knowledge/explanations/` |
| Writing code that calls it | "What's the exact signature?" | Reference | `40-reference/` (generated) |
| Deciding whether to change it | "Why is it this way?" | ADR | `50-decisions/` |
| On-call at 3am | "What do I do?" | Runbook | `60-operations/runbooks/` |
| Planning next quarter | "Where is this going?" | Roadmap/RFC | `80-evolution/` |

If a piece of writing serves two readers in two states, split it.

---

## Appendix B — Frontmatter Schema (Canonical)

```yaml
---
# Required
id: string                  # unique slug, matches filename
title: string               # human-readable
audience: enum              # tutorial | howto | reference | explanation | adr | runbook | meta
tier: int                   # 1 | 2 | 3 | 4
status: enum                # draft | stable | deprecated | removed
owner: string               # @handle or team
last_reviewed: date         # ISO 8601

# Optional but recommended
describes: [path]           # source files this doc claims to describe
depends_on: [doc_id]        # other docs referenced
supersedes: [doc_id]        # older docs this replaces
superseded_by: doc_id       # set when status is deprecated
tags: [string]
related_adrs: [adr_id]
---
```

CI rejects PRs that add or modify docs without valid frontmatter.

---

*This document is itself a doc atom. Its frontmatter would be:*

```yaml
---
id: doc-system
title: A Documentation System for Complex Codebases
audience: reference
tier: 2
status: stable
owner: @anson
last_reviewed: 2026-05-07
describes: []
depends_on: []
---
```
