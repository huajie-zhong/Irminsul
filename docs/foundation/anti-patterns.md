---
id: anti-patterns
title: Anti-Patterns
status: stable
describes: []
---

# Anti-Patterns

These are the failure modes the system exists to prevent. Naming them helps you spot them in code review.

- **The Mega-README.** A single 4,000-line README that documents everything. Fails for humans and causes **Context Dilution** for the agents that read it ([Assumption 1](principles.md#strategic-assumptions)).
- **The Wiki Graveyard.** Docs in a separate Confluence/Notion that drift independently of code. This is a primary source of **Silent Rot** ([Assumption 2](principles.md#strategic-assumptions)).
- **Duplication-by-Paraphrase.** Same fact stated three different ways. Creates the **Contradiction Trap** that triggers hallucinations ([Assumption 2](principles.md#strategic-assumptions)).
- **The Tribal Slack.** Critical decisions made in DMs and Slack threads, never written into ADRs. Violates **Principle 2 (Provenance)**.
- **Doc-as-Changelog.** Component docs that read "We used to do X, then we tried Y, now we do Z." History lives in ADRs; docs should describe present reality only.
- **Ambiguous Documentation Ownership.** Code can evolve without a clear accountable document. Some files have no documented owner; others appear covered by multiple documents, obscuring which one is authoritative.
- **Architecture-Astronaut Diagrams.** A single diagram trying to show everything. C4 levels exist to prevent this — pick a zoom level and stop.
- **Schema Sprawl.** Type definitions appearing in three docs. Prevented by [**Principle 4 (Code is Authoritative for Implementation State)**](principles.md#4-code-is-authoritative-for-implementation-state), the `schema-leak` check, and deriving surfaces on demand (`irminsul surface`).
- **The Inscrutable Acronym.** Domain acronyms used everywhere with no glossary entry. Once a term has an entry, `glossary-discipline` flags unlinked uses and redefinitions; spotting a term that has none is left to review.
