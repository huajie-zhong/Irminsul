---
id: 0002-required-update
title: Required update on the owning component
audience: explanation
tier: 2
status: stable
rfc_state: accepted
affects:
  - auth
resolved_by: docs/50-decisions/0001-adr.md
required_updates:
  - path: docs/20-components/auth.md
    reason: the promoted claim lands here
    kind: update
---

# RFC 0002: Required update on the owning component

The required update is the owning component doc — the backlink finalization
itself writes.

## Requirements

### Requirement: Login flow
ID: login-flow
Provenance: code

Users SHALL be able to log in.

#### Scenario: Valid credentials
- **WHEN** valid credentials are supplied
- **THEN** a session is established

## Resolution

Approved; see [ADR-0001](../../50-decisions/0001-adr.md).
