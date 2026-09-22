---
id: levels-and-views
title: Architecture Levels and Views
status: stable
describes: []
---

# Architecture: Levels and Views

Guidance for projects adopting Irminsul; the file names below are suggestions, and Irminsul itself, a single CLI, needs only an overview. The `architecture/` folder hybridizes two architectural-doc traditions: the C4 zoom levels (Simon Brown) for logical structure, and the 4+1 view model (Kruchten) for cross-cutting concerns that don't fit a single zoom level.

## Levels (Logical Zoom)

- **Level 1 — System Context.** Your system as a single box: users, external systems, boundaries of responsibility. [`architecture/overview.md`](overview.md). Audience: anyone, including non-technical.
- **Level 2 — Containers.** Deployable units (web app, API, worker, DB, queue). `architecture/containers.md`. Audience: any engineer. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->
- **Level 3 — Components.** What lives inside each container. **The entire `components/` folder is L3.** No separate L3 file under architecture.
- **Level 4 — Code.** Omitted. Class and sequence diagrams either generate themselves from code or aren't worth the maintenance.

L1 and L2 are hand-drawn (Mermaid, source-controlled). L3 is the components layer, one doc per component.

## Views (Cross-Cutting Concerns)

Levels are about *zoom*. Views are about *concern* — different lenses on the same architecture. They are not levels; they overlay on L1 and L2.

- **Deployment view.** Where things run: regions, environments, replication, scaling. `architecture/deployment.md`. Overlays on L2. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->
- **Security view.** Trust zones, authentication boundaries, data classification. `architecture/boundaries.md`. Overlays on L1 and L2. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->
- **Data view** (optional). Where data lives, how it flows, retention policy. Useful when data shape dominates design.

This adapts Kruchten's 4+1 view model. The C4 levels are the logical view; deployment and security are alternate views of the same architecture under different concerns. The framing matters because it answers "where does deployment go?" without forcing it into a zoom level it doesn't belong to.
