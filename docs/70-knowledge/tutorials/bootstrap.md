---
id: bootstrap
title: Bootstrapping Checklist
audience: tutorial
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# Bootstrapping Checklist

To adopt this system on a new or existing codebase, in order:

- [ ] Create the `/docs` directory tree (see layers)
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
