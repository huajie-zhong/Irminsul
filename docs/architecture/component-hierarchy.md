---
id: component-hierarchy
title: Component Hierarchy and Doctrine
status: stable
summary: How components nest.
describes: []
claims:
  - id: parent-child-check-available
    state: available
    kind: advisory_check
    relation: follows-evidence
    claim: The parent-child check validates broad INDEX globs and long INDEX bodies.
    evidence:
      - src/irminsul/checks/parent_child.py
      - docs/components/checks.md
    pinned:
      src/irminsul/checks/parent_child.py: sha256:5092bd72cb2c
      docs/components/checks.md: sha256:faf647d9f392
  - id: schema-leak-enabled
    state: enabled
    kind: ci_gate
    relation: follows-evidence
    claim: Schema-leak detection is enabled in this repository and its findings are certain, so CI fails on them.
    evidence:
      - src/irminsul/checks/schema_leak.py
      - .github/workflows/ci.yml
    pinned:
      src/irminsul/checks/schema_leak.py: sha256:ba86a7c46f94
      .github/workflows/ci.yml: sha256:18ef8c6bad1a
---

# Component Hierarchy and Doctrine

A component is a single Markdown file by default. **The hierarchical structure (folder with an index doc plus children) is the exception, not the rule.** It applies only when one file becomes unreadable — rule of thumb: >~500 lines, or covering multiple subsystems each with their own design narrative.

Most components in most codebases stay single-file forever. For those, none of the folder machinery below applies at all. The single file owns its `describes` claim, runs through normal staleness checks, and that's it.

The system never forces the split; the only length warning is for an index doc whose body runs over `length_warning_lines`, because an index is navigation. <!-- anchor: src/irminsul/config.py#ParentChildSettings.length_warning_lines @sha256:3e6ded1bf66c --> Promotion to a folder is a human judgment call:

```
components/
├── composer.md                # Simple: single file
├── interpreter.md
└── planner/                   # Complex: folder
    ├── INDEX.md               # folder index doc, explicit files
    ├── routing.md             # Subsystem doc, its own slice
    ├── caching.md
    └── error-handling.md
```

The folder index doc appears in the components index, claims the component's entry files, and gives the architectural overview. Children describe slices that warrant their own narrative.

## Hierarchical Describes (Specificity Rule)

When components are folders, the coverage-uniqueness rule extends to handle nesting: **exactly one *most-specific* doc claims each source file.** Which of two matching patterns is the more specific is defined once, in the [glossary](../GLOSSARY.md#specificity).

A parent index lists explicit files, never a directory wildcard, so a parent that names one file inside a subfolder is the case this rule resolves:

```yaml
# planner/INDEX.md
describes: [app/planner/plan.py, app/planner/routing/entry.py]
# planner/routing.md
describes: [app/planner/routing/*.py]
```

`entry.py` belongs to the parent: its path has four literal segments against the glob's three, so its claim is the more specific one. The child owns every other file under `app/planner/routing/`, and `plan.py` is the parent's alone. Because the two claims overlap on `entry.py`, one doc must link the other, or `uniqueness` reports the overlap between unlinked docs. <!-- irminsul:ignore code-references reason="files of the example layout" -->

Without the rule, that overlap is a duplicate claim, and the parent could name `entry.py` only if the child dropped its glob and listed every other routing file one by one. The precedent is `.gitignore` and CSS, where the most-specific match wins. From the rule's perspective every source file still has exactly one canonical doc; specificity just picks which one. <!-- irminsul:ignore code-references reason="files of the example layout" -->

## Parent-Child Consistency in Component Folders

Hierarchical describes solves source-file coverage. It does not solve *fact* consistency: a parent index doc and its children can both be currently aligned with their source paths while saying contradictory things about overlapping concerns. Mtime drift won't catch this.

### The Doctrine (Primary Principle)

Parents and children must never document the same *kind* of fact. The folder index doc owns *architecture, integration, intent, contracts* — what the component is, what it exposes, how it fits into the larger system. Children own *implementation* — algorithms, data structures, edge cases.

Same principle as good code design: parent modules expose interfaces, children implement specifics. `planner/INDEX.md` should say "the planner orchestrates routing, caching, and error handling to produce a Plan from a request, with contract `(Request) → Plan | PlanError`." It should NOT say "uses Gemini 2.5 Flash with a 30s timeout" — that's a routing concern, owned by `routing.md`. If a fact could legitimately go in either, it goes in the child by default.

Without doctrine, no mechanical check rescues this — every parent accumulates child-level facts that drift, and contradiction becomes inevitable. With doctrine, contradiction becomes structurally rare.

### Mechanical Enforcement of the Doctrine

Two checks make the highest-frequency doctrine violations costly and visible:

1. **Schema/code-leak detection.** `schema-leak` flags type and schema definitions in any components doc, parent or child, and it is enabled here with certain findings, so CI fails on a leak. An unlabelled fence is read rather than skipped, because that is exactly where a leaked schema would hide. <!-- claim:schema-leak-enabled -->
2. **No broad globs in a parent.** A parent index doc lists explicit files, so the parent-child check reports a directory wildcard in its `describes` as a hint. <!-- claim:parent-child-check-available -->

### The Honest Limit

The semantic boundary between "architectural" and "implementational" cannot be fully mechanized. Two reviewers can legitimately disagree about which side a paragraph falls on. No regex catches "this is too detailed for a parent doc."

The deterministic checks reduce the surface area where doctrine can be violated. The residual semantic cases belong to review — by the humans and coding agents reading the docs — so every PR touching a folder index doc should be reviewed by someone who understands the doctrine.
