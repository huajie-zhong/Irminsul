---
id: principles
title: Principles
audience: explanation
tier: 2
status: stable
describes: []
---

# Principles

Irminsul exists because most documentation rots, and the reason it rots is structural — the system makes the right action harder than the wrong one.

## Strategic Assumptions

Irminsul is built on a specific view of the modern development environment:

1. **LLMs are the primary consumers.** LLM agents are now the most frequent "readers" of documentation. They are exceptionally good at processing volume but exceptionally bad at resolving contradiction.
2. **Rot is the primary failure mode.** The issue isn't that documentation is hard to write; it's that it is impossible to keep accurate as code evolves. "Silent rot"—where docs and code diverge—is the deadliest threat to LLM-driven workflows because it triggers invisible hallucinations.
3. **Principle-first bootstrapping.** A project may begin before code exists. The first useful user input is a well-expressed principle, idea, or belief about what should be built; Irminsul turns that foundation into docs that guide later AI-assisted implementation.
4. **The Harness Principle.** LLMs follow rules most of the time, but they fail silently and confidently. To make LLM-driven development safe, the system must provide **Hard Checks** (deterministic checks). When a check fails, it provides a clear signal that allows the LLM to self-correct without human intervention.
5. **Mechanical Necessity.** We assume that humans will only maintain documentation if the system makes it a mechanical necessity. If the doc doesn't *have* to be updated to merge the code, it eventually won't be.

## The Five Core Principles

### 1. Single Source of Truth (SSOT)
Every fact has exactly one canonical home. All other appearances are references to that home, not copies of it. If you find yourself typing the same definition twice, you've created a future contradiction.

### 2. Provenance
Every non-trivial claim in the docs must trace back to one of three sources: **the source code**, **an Architecture Decision Record (ADR)**, or **an external citation**. Floating assertions ("we use eventual consistency because it's simpler") are forbidden — either point to the ADR that decided it, or write that ADR.

### 3. Audience Separation
Every document is written for one reader in one mental state. The Diataxis framework names four such moments: *learning* (tutorial), *doing* (how-to), *understanding* (explanation), *referring* (reference). A doc that tries to serve two of these serves neither.

### 4. Code as Ultimate Truth
When code and docs disagree, code wins by default. This means anything that *can* be derived from code *should* be — schemas, type signatures, API surfaces, config references, error catalogs — and derived *on demand*, never hand-copied into the docs (see the *Derive, don't materialize* principle below). Hand-written docs cover only what code cannot express: intent, trade-offs, and process.

### 5. The Doc Graph is Bidirectional
If `composer.md` references `data-model.md`, then `data-model.md` should automatically show "referenced by composer.md" at the bottom. Backlinks are generated, not maintained. This makes "what breaks if I change this?" a one-glance question. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->

## Derive, don't materialize

Code is the ultimate truth. Any fact a doc states that is reconstructable from code is a *derivation* of that code, and a committed copy of a derivation is a cache that goes stale. Irminsul does not police stale caches it told you to create — it tells you not to create them.

Every fact a doc can state falls into one of two buckets:

1. **Derivable from code.** Reconstructable from the source: the CLI command list, HTTP endpoints, public exports, env vars read, frontmatter fields, the check registry. The human contributes nothing to the *content* of these facts. Derivable facts are never hand-copied into prose and never committed as a generated artifact. They are **derived on demand** — exposed through a query (`irminsul surface <kind>`) or projected at render time — so they are fresh by construction and cannot drift. A doc that needs them *links or derives*; it does not restate.
2. **Not derivable from code.** Rationale, invariants, the mental model, "why the CLI is thin," design tensions, gotchas — and curated human *intent* about bucket-1 facts ("these are the *public* exports," "these are the commands agents navigate by"). Code cannot produce any of this; it is the doc's real content. It is grounded by claim provenance — pointed at evidence — not surface-diffed, because there is nothing in code to diff it against.

What Irminsul therefore checks:

- **Governance of the non-derivable.** Code is truth for *what*; it is emphatically not truth for *why*. The *why* — rationale, invariants, "the CLI is thin because…", design tensions — is exactly what rots silently and what no compiler ever checks. Claim provenance (claims↔evidence) and why-freshness (semantic and mtime drift) are the real product.
- **Structure of the doc graph.** Coverage, orphans, layering, uniqueness, glossary. These are facts about the documentation *system*, underivable from any single source file.
- **The boundary itself.** A lint that catches a doc hand-copying a derivable fact and says: *derive or link instead.* Keeping each fact in its category is arguably Irminsul's highest-leverage role.

## Goals

- **Mechanical enforcement of structural invariants.** A check that depends on human attention will fail eventually. CI either accepts a PR or doesn't.
- **One fact, one home.** Every domain definition lives in exactly one place. References point at it; copies don't exist.
- **Build correctness never depends on LLM judgment.** Hard checks are pure graph operations, regex, glob resolution, and git arithmetic. LLM checks may exist, but they only ever surface advisories and stay outside the hard profile.
- **Adoption in three commands.** `pipx install irminsul && cd repo && irminsul init` produces a fully wired skeleton. Friction at adoption is fatal.
- **Useful from the first belief.** `irminsul init --fresh` supports a project that starts with only user intent. The user's principle, idea, or belief belongs in foundation docs first; agents can elaborate docs and code from there.

## Non-goals

- **Replacing prose-style linters.** Irminsul checks structure, not prose. Tools like Vale or markdownlint complement it; they don't compete.
- **Hosting docs.** The renderer ships an MkDocs Material backend by design — Irminsul is a *checker*, not a hosting platform.
- **Solving every doc problem.** The reference enumerates failure modes Irminsul deliberately leaves to humans (semantic boundaries between architectural and implementation detail, prose quality, narrative coherence). Where a check can't be made deterministic, the system makes violations costly and easy to spot in review instead.

## Design choices that follow

- **Pure-data language profiles** rather than per-language plugins with behavior. The schema-leak check shouldn't change when we add Go support; only a `LanguageProfile` constant should.
- **CLI + composite Action over GitHub App.** An App is slicker but requires hosted infrastructure. The CLI runs anywhere CI runs, and pre-commit picks it up for free.
- **Most-specific match wins** for the uniqueness check. Without it, hierarchical components (`planner/INDEX.md` claims `app/planner/**`, `planner/routing.md` claims `routing/*.py`) require either no parent claim or per-file delegation lists. CSS specificity is the right precedent. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->
- **Physical co-location implies ownership.** If a Markdown file lives in a folder that has an index doc, it is owned by that index. There is no valid scenario where a file co-locates with an index but is not part of it.
