---
id: principles
title: Principles
audience: explanation
tier: 2
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Principles

Irminsul exists because most documentation rots, and the reason it rots is structural — the system makes the right action harder than the wrong one.

## Strategic Assumptions

Irminsul is built on a specific view of the modern development environment:

1. **LLMs are the primary consumers.** LLM agents are now the most frequent "readers" of documentation. They are exceptionally good at processing volume but exceptionally bad at resolving contradiction.
2. **Rot is the primary failure mode.** The issue isn't that documentation is hard to write; it's that it is impossible to keep accurate as code evolves. "Silent rot"—where docs and code diverge—is the deadliest threat to LLM-driven workflows because it triggers invisible hallucinations.
3. **The Harness Principle.** LLMs follow rules most of the time, but they fail silently and confidently. To make LLM-driven development safe, the system must provide **Hard Checks** (deterministic enforcements). When a check fails, it provides a clear signal that allows the LLM to self-correct without human intervention.
4. **Mechanical Necessity.** We assume that humans will only maintain documentation if the system makes it a mechanical necessity. If the doc doesn't *have* to be updated to merge the code, it eventually won't be.

## The Five Core Principles

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

## Goals

- **Mechanical enforcement of structural invariants.** A check that depends on human attention will fail eventually. CI either accepts a PR or doesn't.
- **One fact, one home.** Every domain definition lives in exactly one place. References point at it; copies don't exist.
- **Build correctness never depends on LLM judgment.** Hard checks are pure graph operations, regex, glob resolution, and git arithmetic. LLM checks may exist, but they only ever surface advisories — never block a merge.
- **Adoption in three commands.** `pipx install irminsul && cd repo && irminsul init` produces a fully wired skeleton. Friction at adoption is fatal.

## Non-goals

- **Replacing prose-style linters.** Irminsul checks structure, not prose. Tools like Vale or markdownlint complement it; they don't compete.
- **Hosting docs.** The renderer ships an MkDocs Material backend by design — Irminsul is a *checker*, not a hosting platform.
- **Solving every doc problem.** The reference enumerates failure modes Irminsul deliberately leaves to humans (semantic boundaries between architectural and implementation detail, prose quality, narrative coherence). Where a check can't be made deterministic, the system makes violations costly and easy to spot in review instead.

## Design choices that follow

- **Pure-data language profiles** rather than per-language plugins with behavior. The schema-leak check shouldn't change when we add Go support; only a `LanguageProfile` constant should.
- **CLI + composite Action over GitHub App.** An App is slicker but requires hosted infrastructure. The CLI runs anywhere CI runs, and pre-commit picks it up for free.
- **Most-specific match wins** for the uniqueness check. Without it, hierarchical components (`planner/INDEX.md` claims `app/planner/**`, `planner/routing.md` claims `routing/*.py`) require either no parent claim or per-file delegation lists. CSS specificity is the right precedent.
- **Physical co-location implies ownership.** If a `.md` file lives in a folder that has an `INDEX.md`, it is owned by that INDEX. There is no valid scenario where a file co-locates with an INDEX but is not part of it.
