---
id: 0008-accepted-no-backlink
title: Accepted RFC whose required update doc lacks implements
status: stable
rfc_state: accepted
affects: []
resolved_by: docs/decisions/0001-good-adr.md
required_updates:
  - path: docs/components/accepted-target.md
    reason: Backlink is only due once this RFC is finalized
    kind: update
---

# RFC 0008: Accepted, no backlink

## Summary

The required update doc exists and lacks `implements`. The RFC is `accepted`,
not `implemented`, so demanding the backlink here would order the author to
write exactly what `rfc-lifecycle` rejects as a hard error.

## Resolution

Accepted.
