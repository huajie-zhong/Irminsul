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

- **The Mega-README.** A single 4,000-line README that documents everything. Dies because nobody reads past the install instructions, and updates fight for the same lines.
- **The Wiki Graveyard.** Docs in a separate Confluence/Notion that drift independently of code. Defeats the Change Triplet by making doc updates a separate workflow.
- **Duplication-by-Paraphrase.** Same fact stated three different ways across three docs, none of them clearly canonical. Worse than verbatim duplication because diff tools can't catch it.
- **The Tribal Slack.** Critical decisions made in DMs and Slack threads, never written into ADRs. Six months later nobody remembers why.
- **Doc-as-Changelog.** Component docs that read "We used to do X, then we tried Y, now we do Z." They should describe present reality only. History lives in ADRs and git log.
- **The Phantom Owner.** Docs with no `owner` field, or with an owner who left the org. CI should fail PRs that introduce these.
- **Architecture-Astronaut Diagrams.** A single diagram trying to show everything, which ends up showing nothing. C4 levels exist to prevent this — pick a zoom level and stop.
- **Schema Sprawl.** Type definitions appearing in three docs. T1 generation prevents this categorically.
- **The Inscrutable Acronym.** Domain acronyms used everywhere with no glossary entry. The glossary linter catches this.
