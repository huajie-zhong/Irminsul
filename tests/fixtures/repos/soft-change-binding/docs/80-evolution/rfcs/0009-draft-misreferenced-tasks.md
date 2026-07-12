---
id: 0009-draft-misreferenced-tasks
title: Draft RFC with mis-referenced tasks
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects:
  - auth
---

# RFC 0009: Mis-referenced tasks

References that the trailing-reference grammar would otherwise swallow.

## Requirements

### Requirement: Token refresh
ID: token-refresh
Provenance: code

The client MUST refresh an expiring token.

#### Scenario: Expiring token
- **WHEN** the token is close to expiry
- **THEN** it is refreshed

#### Scenario: Expired token
- **WHEN** the token is already expired
- **THEN** the session is ended

## Tasks

- `T1` Refresh the token. (req: token-refresh) (component: auth)
- `T2` (req: token-refresh) then trailing prose.
- `T3` Legitimate task. (req: token-refresh)
