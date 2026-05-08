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

Irminsul exists because most documentation rots, and the reason it rots is structural — the system makes the right action harder than the wrong one. The full reasoning lives in [the reference](../90-meta/doc-system.md). This file names the principles that drive the tool's design.

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
