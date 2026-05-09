---
id: rfc-0005
title: Systemic Doc Enforcement (Reality, Coverage, Boundary, Liar)
audience: reference
tier: 4
status: draft
owner: "@gemini"
last_reviewed: 2026-05-09
describes: []
---

# RFC 0005: Systemic Doc Enforcement

## Problem
Current documentation in Irminsul (and projects using it) suffers from four distinct types of "truth rot" that are difficult for agents and humans to detect without deep source-code inspection:
1. **Speculative Reality:** Component docs describing future/deferred features as if they are part of the current architecture.
2. **Verification Blindness:** No machine-verifiable link between a component doc and the tests that verify its described source.
3. **Ambiguous Silence:** Undocumented limitations (e.g., lack of retries) that require reading implementation code to discover.
4. **Tier Mismatch (The Liar):** Living docs (T3) manually duplicating field descriptions that should be auto-generated (T1).

## Proposal

We propose four new checks to be added to the Irminsul core:

### 1. `RealityCheck` (Soft/Advisory)
Scans Tier 3 (Living) documents for speculative keywords ("planned", "deferred", "sprint", "roadmap", "v0.X"). 
*   **Rule:** Living component docs must reflect the state of the current branch. Future plans belong in RFCs or the Roadmap.

### 2. `CoverageCheck` (Hard)
Introduces a mandatory `tests:` field in the `DocAtom` frontmatter for Tier 3 docs.
*   **Rule:** Every T3 doc must point to at least one valid test file/directory.
*   **Benefit:** Allows agents and CI to run targeted tests for documentation changes.

### 3. `BoundaryCheck` (Advisory)
Enforces a "Scope & Limitations" section in T3 component templates.
*   **Rule:** Docs must explicitly state what the component *does not* do to reduce "guessing" from callers and AI agents.

### 4. `LiarCheck` (Hard)
Detects duplication between T3 (Living) and T1 (Generated) docs.
*   **Rule:** If a T3 doc describes a file covered by T1 generation (e.g., Pydantic models), it must not manually list field names/signatures without a reference link to the T1 doc.

## Implementation Plan
1. Update `irminsul new component` template to include `tests:` frontmatter and `## Scope & Limitations` section.
2. Implement `CoverageCheck` in `src/irminsul/checks/coverage.py`.
3. Implement keyword-based `RealityCheck` and `LiarCheck` as part of the `checks` suite.
