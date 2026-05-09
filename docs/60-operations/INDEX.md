---
id: 60-operations
title: Operations
audience: reference
tier: 3
status: draft
describes: []
tests:
  - tests/
---

# Operations

Runbooks, playbooks, SLOs, observability strategy, on-call rotation.

## Runbooks

Runbooks live in `runbooks/` and exist for one purpose: to be useful at 3am when an alert fires. Optimize aggressively for that moment.

Structure (same skeleton for every runbook, no exceptions):

1. **Symptom** — the exact alert text or observable behavior. This is the search target. Runbook IDs should match alert IDs in your monitoring system, so the alert page links directly to the runbook.
2. **Quick Mitigation** — the dumbest thing that often works. Restart, scale up, fail over. This is what a tired on-call engineer does first.
3. **Diagnosis Tree** — branching checks: "if X is high, then Y; if Z is timing out, then W."
4. **Root Cause Investigation** — once stable, the deeper analysis steps.
5. **What NOT to Do** — common mistakes that worsen the incident. Critically important and almost always omitted from runbooks. This is often the most valuable section.
6. **Postmortem Template Link** — direct link to the postmortem doc to fill out after.

Two staleness defenses specific to runbooks:

- **Last Validated.** Frontmatter field updated whenever on-call confirms the runbook actually worked. CI flags runbooks not validated in 6 months.
- **Game Days.** Scheduled exercises where the team manually triggers a scenario in non-prod and runs the runbook end-to-end. Catches drift no static check can.
