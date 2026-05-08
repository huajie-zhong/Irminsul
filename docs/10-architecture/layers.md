---
id: layers
title: The Layered Directory Structure
audience: explanation
tier: 2
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes: []
---

# The Layered Directory Structure

The numeric prefixes in the `docs/` folder serve two purposes: stable sort order for humans browsing the tree, and namespacing so doc IDs can use bare slugs (`composer` rather than `components/composer`).

```
/docs
├── README.md                      # Map of the system
├── GLOSSARY.md                    # Canonical vocabulary (the dictionary)
├── CONTRIBUTING.md                # How to write docs in this system
│
├── 00-foundation/                 # Things that rarely change (T2)
│   ├── principles.md              # Goals, non-goals, design philosophy
│   ├── constraints.md             # Technical, business, ethical limits
│   └── stakeholders.md            # Who this exists for
│
├── 10-architecture/               # The "what" (T2)
│   ├── overview.md                # C4 Level 1: System Context
│   ├── containers.md              # C4 Level 2: Containers (services, DBs, queues)
│   ├── boundaries.md              # Trust zones, security boundaries
│   └── deployment.md              # Topology, environments, regions
│
├── 20-components/                 # The "what" at component level (T3)
│   ├── INDEX.md                   # Auto-generated from frontmatter
│   ├── composer.md                # Simple component: single file
│   ├── interpreter.md
│   └── planner/                   # Complex component: folder
│       ├── INDEX.md               # L3 entry, broad describes
│       ├── routing.md             # Narrower describes
│       └── caching.md
│
├── 30-workflows/                  # Cross-component "how" (T3)
│   ├── INDEX.md
│   ├── generation-pipeline.md
│   ├── auth-flow.md
│   └── ...
│
├── 40-reference/                  # Generated. Do not edit by hand. (T1)
│   ├── api/                       # OpenAPI-rendered or auto-extracted
│   ├── schema/                    # Pydantic/Zod/Proto → Markdown
│   ├── config/                    # Settings reference
│   ├── events/                    # Event catalog
│   └── errors/                    # Error code dictionary
│
├── 50-decisions/                  # The "why" (T2, append-only)
│   ├── INDEX.md
│   ├── 0001-monorepo-vs-polyrepo.md
│   ├── 0002-pydantic-not-dsl.md
│   └── ...
│
├── 60-operations/                 # Run the thing (T3)
│   ├── runbooks/                  # Step-by-step for known incidents
│   ├── playbooks/                 # Recurring ops procedures
│   ├── slos.md                    # Service-level objectives
│   ├── observability.md           # Metrics, logs, traces strategy
│   └── oncall.md
│
├── 70-knowledge/                  # Audience-facing learning (T3)
│   ├── tutorials/                 # Learning-oriented (Diataxis)
│   ├── howtos/                    # Task-oriented (Diataxis)
│   └── explanations/              # Understanding-oriented (Diataxis)
│
├── 80-evolution/                  # Where the system is going (T4 mostly)
│   ├── roadmap.md
│   ├── rfcs/                      # Proposals before decisions
│   ├── risks.md                   # Risk register
│   ├── debt.md                    # Tech debt registry
│   └── deprecations.md            # What's going away and when
│
└── 90-meta/                       # Docs about docs
    ├── style-guide.md
    └── health-dashboard.md        # Auto-generated metrics
```
