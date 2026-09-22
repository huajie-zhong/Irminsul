---
id: 0007-depends-on-only
title: Implemented RFC whose update doc only depends on it
status: stable
rfc_state: implemented
resolved_by: docs/decisions/0001-good-adr.md
required_updates:
- path: docs/components/depends-on-only.md
  reason: Depends-on is not an implementation backlink
  kind: update
---

# RFC 0007: Depends-on only

## Summary

The required update doc uses `depends_on` but omits `implements`.

## Resolution

Accepted.
