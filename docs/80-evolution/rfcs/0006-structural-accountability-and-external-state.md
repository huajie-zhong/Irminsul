---
id: 0006-structural-accountability-and-external-state
title: Structural Accountability & External State Verification
audience: reference
tier: 4
status: draft
owner: "@gemini"
last_reviewed: 2026-05-09
describes: []
---

# RFC 0006: Structural Accountability & External State

## Problem
Currently, documentation dependencies (`depends_on`) and external requirements (environment variables) are manual, unvalidated strings. This leads to:
1. **Hallucination:** Adding fake dependencies to "silence" orphan warnings.
2. **Staleness:** Keeping requirements/dependencies in docs after they are removed from code.
3. **Implicit Friction:** Agents must hunt for "entry points" and "hidden env vars" by reading all files in a component glob.

## Proposal

### 1. Transitive `requires_env` Verification
Introduce a `requires_env: []` list in Tier 3 frontmatter.
- **Mechanical Existence:** CI scans code for `os.environ.get()` and `os.getenv()`. Every key found must exist in the component's `requires_env` or its dependencies.
- **Mechanical Staleness:** If a key is listed in frontmatter but does not exist in the described code, it is flagged as stale.
- **Transitive Pass:** If Doc A `depends_on` Doc B, Doc A can use any env var defined in Doc B without re-declaring it.

### 2. Import-Based `depends_on` Validation
Transform `depends_on` from a conceptual list to a verified architectural graph.
- **Hallucination Gate:** `depends_on: [TargetID]` is only valid if the source files described by the current doc physically import files described by the `TargetID`.
- **Stale Reaper:** If an import is removed, the dependency must be removed from the doc atom.
- **Reciprocity:** Automated backlinks are generated from `depends_on` to facilitate "What breaks if I change this?" queries.

### 3. The "First-is-Interface" Convention
- **Rule:** The first file/glob listed in the `describes:` field is formally recognized as the **Entry Point** or **Interface** of the component.
- **Benefit:** Reduces agent/human exploration cost. When seeking to understand a component's API, always start with the first file in `describes`.

### 4. Phantom Layer Enforcement
- **Rule:** Any directory mapped in `docs/README.md` or templates must contain at least one valid `INDEX.md` and non-empty content.
- **Enforcement:** `irminsul check` will flag "Phantom Layers" to prevent navigation rot.

## Implementation Plan
1. Update `DocFrontmatter` schema to include `requires_env`.
2. Implement `EnvCheck` using static analysis (regex/ast) on `describes` targets.
3. Implement `DependencyCheck` by cross-referencing file imports with the `DocGraph`.
4. Update `init` templates to remove empty "Phantom" directories (`30-workflows`, `60-operations`) until they have content.
