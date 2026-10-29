---
id: principles
title: Principles
status: stable
summary: The five core principles and the three laws of maintenance.
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

Code is not authoritative for intent, constraints, semantic models, or rationale: an implementation that violates a stated constraint is a defect, not a correction. Otherwise the foundation would be advisory, and anything an agent shipped would become the rule ([authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)).

### 5. The Doc Graph is Bidirectional
If `composer.md` references `data-model.md`, then `irminsul refs data-model` lists `composer.md`. Backlinks are derived on demand, not maintained by hand. This makes "what breaks if I change this?" a one-command question. <!-- irminsul:ignore code-references reason="example skeleton" -->

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

1. **Mechanically reconstructable from code.** Rebuildable from the source without semantic judgment: the CLI command list, HTTP endpoints, public exports, env vars read, frontmatter fields, the check registry. The human contributes nothing to the *content* of these facts, so they are never hand-copied into prose or committed as a generated artifact. They are **derived on demand** through a query (`irminsul surface <kind>`), fresh by construction, and a doc that needs them *links or derives*; it does not restate.
2. **Not mechanically reconstructable.** Rationale, invariants, the mental model, "why the CLI is thin," design tensions, gotchas — and curated human *intent* about bucket-1 facts ("these are the *public* exports," "these are the commands agents navigate by"). Code cannot produce any of this; it is the doc's real content. It is grounded by claim provenance — pointed at evidence — not surface-diffed, because there is nothing in code to diff it against.

What Irminsul therefore checks:

- **Governance of the non-derivable.** Code is authoritative for the *what* it can be made to prove; it is emphatically not authoritative for *why*, nor for a *what* that only a reader can piece together. The *why* — rationale, invariants, "the CLI is thin because…", design tensions — is exactly what rots silently and what no compiler ever checks. Claim provenance (claims↔evidence) and why-freshness (anchored claims, mtime drift, and the review queue) are the real product.
- **Structure of the doc graph.** Coverage, orphans, layering, uniqueness, glossary. These are facts about the documentation *system*, underivable from any single source file.
- **The boundary itself.** A doc names the code it means in code spans, and an `inventory:` entry checks a list it curates against the code, so a derivable fact is linked or derived rather than copied ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)). Keeping each fact in its category is arguably Irminsul's highest-leverage role.

## Goals

- **Mechanical enforcement of structural invariants.** A check that depends on human attention will fail eventually. CI either accepts a PR or doesn't.
- **One fact, one home.** Every domain definition lives in exactly one place. References point at it; copies don't exist.
- **Build correctness never depends on LLM judgment.** Irminsul makes no LLM calls; every check is deterministic, and semantic judgment belongs to the coding agent consuming Irminsul, not to the tool itself.
- **Adoption in four commands.** An existing codebase gets a fully wired skeleton, and a run that its undocumented files do not fail, from the four commands of the [README](../../README.md) quickstart. Friction at adoption is fatal.
- **Useful from the first belief.** A project that has only its principles, and no code yet, gets the same skeleton and gates ([Assumption 3](#strategic-assumptions)).

## Non-goals

- **Replacing prose-style linters.** Irminsul checks structure, not prose. Tools like Vale or markdownlint complement it; they don't compete.
- **Hosting docs.** Irminsul is a *checker*, not a hosting platform. The markdown tree is portable; point any static-site generator at it if you want a published site.
- **Solving every doc problem.** Irminsul deliberately leaves some failure modes to humans (semantic boundaries between architectural and implementation detail, prose quality, narrative coherence). Where a check can't be made deterministic, the system makes violations costly and easy to spot in review instead.
