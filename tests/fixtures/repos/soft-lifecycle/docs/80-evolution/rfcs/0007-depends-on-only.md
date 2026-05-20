---
id: 0007-depends-on-only
title: Accepted RFC whose update doc only depends on it
audience: explanation
tier: 2
status: stable
rfc_state: accepted
resolved_by: docs/50-decisions/0001-good-adr.md
required_updates:
  - path: docs/20-components/depends-on-only.md
    reason: Depends-on is not an implementation backlink
    kind: update
---

# RFC 0007: Depends-on only

## Summary

The required update doc uses `depends_on` but omits `implements`.

## Resolution

Accepted.
