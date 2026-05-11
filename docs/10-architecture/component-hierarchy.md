---
id: component-hierarchy
title: Component Hierarchy and Doctrine
audience: explanation
tier: 2
status: stable
describes: []
claims:
  - id: parent-child-check-available
    state: available
    kind: advisory_check
    claim: The parent-child check validates broad INDEX globs and long INDEX bodies.
    evidence:
      - src/irminsul/checks/parent_child.py
      - docs/40-reference/check-registries.md
  - id: schema-leak-enabled
    state: enabled
    kind: ci_gate
    claim: Schema-leak detection is part of the hard check profile run by this repository's CI.
    evidence:
      - src/irminsul/checks/schema_leak.py
      - .github/workflows/ci.yml
  - id: llm-scope-available
    state: available
    kind: advisory_check
    claim: LLM scope and semantic checks are available as advisory checks.
    evidence:
      - src/irminsul/checks/scope_appropriateness.py
      - docs/40-reference/check-registries.md
---

# Component Hierarchy and Doctrine

A component is a single Markdown file by default. **The hierarchical structure (folder with an index doc plus children) is the exception, not the rule.** It applies only when one file becomes unreadable — rule of thumb: >~500 lines, or covering multiple subsystems each with their own design narrative.

Most components in most codebases stay single-file forever. For those, none of the parent-child machinery in the next subsection applies at all. The single file owns its `describes` claim, runs through normal staleness checks, and that's it.

The system warns when a doc exceeds an extreme length (~800 lines) but never forces the split. Promotion to a folder is a human judgment call, made when one file genuinely doesn't fit anymore:

```
20-components/
├── composer.md                # Simple: single file
├── interpreter.md
└── planner/                   # Complex: folder
    ├── INDEX.md               # L3 entry, broad describes <!-- irminsul:ignore prose-file-reference reason="example tree" -->
    ├── routing.md             # Subsystem doc, narrower describes
    ├── caching.md
    └── error-handling.md
```

The folder index doc is the L3 entry — it appears in the components index, holds the broad `describes` claim, and gives the architectural overview. Children describe slices that warrant their own narrative.

## Hierarchical Describes (Specificity Rule)

When components are folders, the coverage-uniqueness rule extends to handle nesting: **exactly one *most-specific* doc claims each source file.** A child doc claiming `app/planner/routing/*.py` shadows the parent's claim of `app/planner/*.py` for exactly those files. The parent retains authority over everything not shadowed.

This pattern matches `.gitignore` and CSS specificity — the most-specific match wins. CI builds the claim graph at validation time and resolves shadowing before the uniqueness check runs. From the rule's perspective every source file still has exactly one canonical doc; specificity just picks which one.

## Parent-Child Consistency in Component Folders

**This subsection only applies when a component is a folder.** Single-file components have no parent-child concern.

Hierarchical describes solves source-file coverage. It does not solve *fact* consistency: a parent index doc and its children can both be currently aligned with their source paths while saying contradictory things about overlapping concerns. Mtime drift won't catch this.

### The Doctrine (Primary Principle)

Parents and children must never document the same *kind* of fact. The folder index doc owns *architecture, integration, intent, contracts* — what the component is, what it exposes, how it fits into the larger system. Children own *implementation* — algorithms, data structures, edge cases.

Same principle as good code design: parent modules expose interfaces, children implement specifics. `planner/INDEX.md` should say "the planner orchestrates routing, caching, and error handling to produce a Plan from a request, with contract `(Request) → Plan | PlanError`." It should NOT say "uses Gemini 2.5 Flash with a 30s timeout" — that's a routing concern, owned by `routing.md`. If a fact could legitimately go in either, it goes in the child by default. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->

Without doctrine, no mechanical check rescues this — every parent accumulates child-level facts that drift, and contradiction becomes inevitable. With doctrine, contradiction becomes structurally rare.

### Mechanical Enforcement of the Doctrine

Several checks make the highest-frequency doctrine violations costly and visible:

1. **Schema/code-leak detection in parent index docs.** The schema-leak rule applies extra strictly to parent docs: regex bans on class definitions, type signatures, specific library-version strings, and substantive code blocks. These belong in children. <!-- claim:schema-leak-enabled -->
2. **No-broad-globs in parents-with-children.** If a folder has children, its index doc's `describes` field must be empty or an explicit list of files — never directory wildcards. The parent-child check reports an error on broad globs in parent docs. <!-- claim:parent-child-check-available -->
3. **Length cap as smell.** Warn if an index doc exceeds ~300 lines. Architecture writing should be concise; long parents indicate accumulated implementation detail. Advisory.
4. **Folder auto-ownership.** An `INDEX.md` auto-owns sibling docs in its folder. No `children:` registry is required. <!-- irminsul:ignore prose-file-reference reason="literal filename rule" -->
5. **LLM contradiction and scope checks.** Advisory LLM checks can flag semantic overlap, drift, or inappropriate detail. They are review signals, not hard gates. <!-- claim:llm-scope-available -->

### The Honest Limit

The semantic boundary between "architectural" and "implementational" cannot be fully mechanized. Two reviewers can legitimately disagree about which side a paragraph falls on. No regex catches "this is too detailed for a parent doc."

The deterministic checks reduce the surface area where doctrine can be violated. The LLM advisory checks catch a fraction of the residual semantic cases. Everything else is review quality — every PR touching a folder index doc should be reviewed by someone who understands the doctrine.
