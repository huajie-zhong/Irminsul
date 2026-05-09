---
id: component-hierarchy
title: Component Hierarchy and Doctrine
audience: explanation
tier: 2
status: stable
describes: []
---

# Component Hierarchy and Doctrine

A component is a single `.md` file by default. **The hierarchical structure (folder with INDEX.md plus children) is the exception, not the rule.** It applies only when one file becomes unreadable — rule of thumb: >~500 lines, or covering multiple subsystems each with their own design narrative.

Most components in most codebases stay single-file forever. For those, none of the parent-child machinery in the next subsection (doctrine, mtime cascade, children registry, contradiction detector) applies at all. The single file owns its `describes` claim, runs through normal staleness checks, and that's it.

The system warns when a doc exceeds an extreme length (~800 lines) but never forces the split. Promotion to a folder is a human judgment call, made when one file genuinely doesn't fit anymore:

```
20-components/
├── composer.md                # Simple: single file
├── interpreter.md
└── planner/                   # Complex: folder
    ├── INDEX.md               # L3 entry, broad describes
    ├── routing.md             # Subsystem doc, narrower describes
    ├── caching.md
    └── error-handling.md
```

The INDEX.md is the L3 entry — it appears in the components index, holds the broad `describes` claim, and gives the architectural overview. Children describe slices that warrant their own narrative.

## Hierarchical Describes (Specificity Rule)

When components are folders, the coverage-uniqueness rule extends to handle nesting: **exactly one *most-specific* doc claims each source file.** A child doc claiming `app/planner/routing/*.py` shadows the parent's claim of `app/planner/*.py` for exactly those files. The parent retains authority over everything not shadowed.

This pattern matches `.gitignore` and CSS specificity — the most-specific match wins. CI builds the claim graph at validation time and resolves shadowing before the uniqueness check runs. From the rule's perspective every source file still has exactly one canonical doc; specificity just picks which one.

## Parent-Child Consistency in Component Folders

**This subsection only applies when a component is a folder.** Single-file components have no parent-child concern.

Hierarchical describes solves *file* coverage. It does not solve *fact* consistency: a parent INDEX.md and its children can both be currently aligned with their source paths while saying contradictory things about overlapping concerns. Mtime drift won't catch this.

### The Doctrine (Primary Principle)

Parents and children must never document the same *kind* of fact. The folder INDEX.md owns *architecture, integration, intent, contracts* — what the component is, what it exposes, how it fits into the larger system. Children own *implementation* — algorithms, data structures, edge cases.

Same principle as good code design: parent modules expose interfaces, children implement specifics. `planner/INDEX.md` should say "the planner orchestrates routing, caching, and error handling to produce a Plan from a request, with contract `(Request) → Plan | PlanError`." It should NOT say "uses Gemini 2.5 Flash with a 30s timeout" — that's a routing concern, owned by `routing.md`. If a fact could legitimately go in either, it goes in the child by default.

Without doctrine, no mechanical check rescues this — every parent accumulates child-level facts that drift, and contradiction becomes inevitable. With doctrine, contradiction becomes structurally rare.

### Mechanical Enforcement of the Doctrine

Several checks make the highest-frequency doctrine violations costly and visible. These are deterministic and build-blocking unless noted:

1. **Schema/code-leak detection in parent INDEX.md.** The schema-leak rule applies extra strictly to parent docs: regex bans on class definitions, type signatures, specific library-version strings, and substantive code blocks. These belong in children.
2. **No-broad-globs in parents-with-children.** If a folder has children, its INDEX.md's `describes` field must be empty or an explicit list of files — never directory wildcards. Forces the parent to declare exactly what it owns versus what it delegates to children. Build fails on broad globs in parent docs.
3. **Length cap as smell.** Warn if an INDEX.md exceeds ~300 lines. Architecture writing should be concise; long parents indicate accumulated implementation detail. Advisory.
4. **Children registry consistency.** The folder's INDEX.md declares `children: [routing, caching, error-handling]` in frontmatter. CI verifies this matches the folder contents on disk. Adding or removing a child without updating the registry fails the build — forces an explicit decision about whether the parent narrative needs to acknowledge the change.
5. **Mtime cascade.** A parent's *effective* mtime is `max(own_mtime, max(child_mtimes))`. When any child is edited substantively, the parent's effective mtime updates and the staleness check re-evaluates against the parent's `last_reviewed` field. If the parent hasn't been reviewed since a child was rewritten, the renderer injects a `[CHILD-DRIFT]` badge. Advisory, not blocking.
6. **LLM contradiction detector (advisory).** Nightly job reads each parent together with all its children and asks the model to flag direct contradictions. Catches cases where two prose statements happen to disagree (parent says "synchronous flow," child says "events queue for async processing"). Opens an issue, never blocks.
7. **LLM scope-appropriateness check (advisory).** Reads each parent and flags paragraphs that look like implementation detail rather than architecture/integration. Opens an issue, never blocks.

### The Honest Limit

The semantic boundary between "architectural" and "implementational" cannot be fully mechanized. Two reviewers can legitimately disagree about which side a paragraph falls on. No regex catches "this is too detailed for a parent doc."

The deterministic checks (1–5) reduce the surface area where doctrine can be violated. The LLM advisory checks (6, 7) catch a fraction of the residual semantic cases. Everything else is review quality — every PR touching an INDEX.md should be reviewed by someone who understands the doctrine, and the children-registry rule (4) guarantees such PRs always exist when structure changes.
