---
id: anti-patterns
title: Anti-Patterns
audience: explanation
tier: 2
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Anti-Patterns

These are the failure modes the system exists to prevent. Naming them helps you spot them in code review.

- **The Mega-README.** A single 4,000-line README that documents everything. Fails for humans and causes **Context Dilution** for LLMs ([Assumptions 1 & 3](principles.md#strategic-assumptions)).
- **The Wiki Graveyard.** Docs in a separate Confluence/Notion that drift independently of code. This is a primary source of **Silent Rot** ([Assumption 2](principles.md#strategic-assumptions)).
- **Duplication-by-Paraphrase.** Same fact stated three different ways. Creates the **Contradiction Trap** that triggers hallucinations ([Assumption 1](principles.md#strategic-assumptions)).
- **The Tribal Slack.** Critical decisions made in DMs and Slack threads, never written into ADRs. Violates **Principle 2 (Provenance)**.
- **Doc-as-Changelog.** Component docs that read "We used to do X, then we tried Y, now we do Z." History lives in ADRs; docs should describe present reality only.
- **The Phantom Owner.** Docs with no `owner` field, or with an owner who left the org. Violates the accountability requirement of Tier 2 docs.
- **Architecture-Astronaut Diagrams.** A single diagram trying to show everything. C4 levels exist to prevent this — pick a zoom level and stop.
- **Schema Sprawl.** Type definitions appearing in three docs. Prevented by **Principle 4 (Code as Ultimate Truth)** and T1 generation.
- **The Inscrutable Acronym.** Domain acronyms used everywhere with no glossary entry. The glossary linter catches this.
