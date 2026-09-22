---
id: principles
title: Principles
status: stable
describes: []
---

# Principles

Irminsul exists because most documentation rots, and the reason it rots is structural — the system makes the right action harder than the wrong one.

## Strategic Assumptions

Irminsul is built on a specific view of the modern development environment:

1. **Agents operate; humans authorize.** Agents are the primary operators and direct consumers of repository knowledge; humans interact with that knowledge primarily through agents and remain the authority for intent and approval.
2. **Rot is the primary failure mode.** The issue isn't that documentation is hard to write; it's that it is impossible to keep accurate as code evolves. "Silent rot"—where docs and code diverge—is the deadliest threat to LLM-driven workflows because it triggers invisible hallucinations.
3. **Principle-first bootstrapping.** A project may begin before code exists. The first useful user input is a well-expressed principle, idea, or belief about what should be built; Irminsul turns that foundation into docs that guide later AI-assisted implementation.
4. **The Harness Principle.** LLMs follow rules most of the time, but they fail silently and confidently. To make LLM-driven development safe, the system must provide deterministic checks that fail on what they can prove. When a check fails, it provides a clear signal that allows the LLM to self-correct without human intervention.
5. **Mechanical Necessity.** We assume that humans will only maintain documentation if the system makes it a mechanical necessity. If the doc doesn't *have* to be updated to merge the code, it eventually won't be.

## The Five Core Principles

### 1. Single Source of Truth (SSOT)
Every fact has exactly one canonical home. All other appearances are references to that home, not copies of it. If you find yourself typing the same definition twice, you've created a future contradiction. Which home is canonical depends on the kind of claim: implementation state answers to code, intent and constraint to authored knowledge, rationale to the record that decided it.

### 2. Provenance
Every non-trivial claim in the docs must trace back to one of three sources: **the source code**, **an Architecture Decision Record (ADR)**, or **an external citation**. Floating assertions ("we use eventual consistency because it's simpler") are forbidden — either point to the ADR that decided it, or write that ADR.

### 3. Audience Separation
Every document is written for one reader in one mental state. The Diataxis framework names four such moments: *learning* (tutorial), *doing* (how-to), *understanding* (explanation), *referring* (reference). A doc that tries to serve two of these serves neither.

### 4. Code is Authoritative for Implementation State
Code wins on what it can be made to prove: **mechanically reconstructable implementation state** — schemas, type signatures, API surfaces, config references, error catalogs. Those are derived *on demand*, never hand-copied into the docs (see the *Derive, don't materialize* principle below), and a doc that disagrees with them is the thing that is wrong.

Code is not authoritative for intent, constraints, semantic models, or rationale. An implementation that violates a stated constraint is a defect, not a correction — otherwise the foundation would be advisory, and anything an agent shipped would retroactively become the rule. Note that *inferable from code* is a wider net than *mechanically reconstructable*: a mental model a reader could piece together from twenty files is authored knowledge, not a derivable surface ([authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)).

### 5. The Doc Graph is Bidirectional
If `composer.md` references `data-model.md`, then `irminsul refs data-model` lists `composer.md`. Backlinks are derived on demand, not maintained by hand. This makes "what breaks if I change this?" a one-command question. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->

## The Three Laws of Maintenance

These are the operational consequences of the core principles, simple enough to check mechanically. When something feels wrong with a doc, ask which law it violates; the answer almost always points at the fix.

> **Law 1.** Each fact has exactly one home.
>
> **Law 2.** Each document has exactly one purpose and one audience moment.
>
> **Law 3.** Every cross-reference is machine-verifiable and can be followed in both directions.

## Derive, don't materialize

Code is authoritative for implementation state. Any fact a doc states that is mechanically reconstructable from code is a *derivation* of that code, and a committed copy of a derivation is a cache that goes stale. Irminsul does not police stale caches it told you to create — it tells you not to create them.

Every fact a doc can state falls into one of two buckets:

1. **Mechanically reconstructable from code.** Rebuildable from the source without semantic judgment: the CLI command list, HTTP endpoints, public exports, env vars read, frontmatter fields, the check registry. The human contributes nothing to the *content* of these facts. Derivable facts are never hand-copied into prose and never committed as a generated artifact. They are **derived on demand** — exposed through a query (`irminsul surface <kind>`) — so they are fresh by construction and cannot drift. A doc that needs them *links or derives*; it does not restate.
2. **Not mechanically reconstructable.** Rationale, invariants, the mental model, "why the CLI is thin," design tensions, gotchas — and curated human *intent* about bucket-1 facts ("these are the *public* exports," "these are the commands agents navigate by"). Code cannot produce any of this; it is the doc's real content. It is grounded by claim provenance — pointed at evidence — not surface-diffed, because there is nothing in code to diff it against.

What Irminsul therefore checks:

- **Governance of the non-derivable.** Code is authoritative for the *what* it can be made to prove; it is emphatically not authoritative for *why*, nor for a *what* that only a reader can piece together. The *why* — rationale, invariants, "the CLI is thin because…", design tensions — is exactly what rots silently and what no compiler ever checks. Claim provenance (claims↔evidence) and why-freshness (anchored claims, mtime drift, and the review queue) are the real product.
- **Structure of the doc graph.** Coverage, orphans, layering, uniqueness, glossary. These are facts about the documentation *system*, underivable from any single source file.
- **The boundary itself.** A lint that catches a doc hand-copying a derivable fact and says: *derive or link instead.* Keeping each fact in its category is arguably Irminsul's highest-leverage role.

## Goals

- **Mechanical enforcement of structural invariants.** A check that depends on human attention will fail eventually. CI either accepts a PR or doesn't.
- **One fact, one home.** Every domain definition lives in exactly one place. References point at it; copies don't exist.
- **Build correctness never depends on LLM judgment.** Checks are pure graph operations, regex, glob resolution, and git arithmetic. Irminsul makes no LLM calls at all — every check is deterministic. Semantic judgment belongs to the coding agent consuming Irminsul, not to the tool itself.
- **Adoption in three commands.** `pipx install irminsul && cd repo && irminsul init` produces a fully wired skeleton. Friction at adoption is fatal.
- **Useful from the first belief.** `irminsul init --fresh` supports a project that starts with only user intent. The user's principle, idea, or belief belongs in foundation docs first; agents can elaborate docs and code from there.

## Non-goals

- **Replacing prose-style linters.** Irminsul checks structure, not prose. Tools like Vale or markdownlint complement it; they don't compete.
- **Hosting docs.** Irminsul is a *checker*, not a hosting platform. The markdown tree is portable; point any static-site generator at it if you want a published site.
- **Solving every doc problem.** Irminsul deliberately leaves some failure modes to humans (semantic boundaries between architectural and implementation detail, prose quality, narrative coherence). Where a check can't be made deterministic, the system makes violations costly and easy to spot in review instead.

## Design choices that follow

- **Pure-data language profiles** rather than per-language plugins with behavior. Adding a language adds a `LanguageProfile` constant; the schema-leak check does not change.
- **CLI + composite Action over GitHub App.** An App is slicker but requires hosted infrastructure. The CLI runs anywhere CI runs, and a project can call it from its own pre-commit hook.
- **Most-specific match wins** for the uniqueness check. Without it, hierarchical components (`planner/INDEX.md` claims `app/planner/**`, `planner/routing.md` claims `routing/*.py`) require either no parent claim or per-file delegation lists. CSS specificity is the right precedent. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->
- **Physical co-location implies ownership.** If a Markdown file lives in a folder that has an index doc, it is owned by that index. There is no valid scenario where a file co-locates with an index but is not part of it.
