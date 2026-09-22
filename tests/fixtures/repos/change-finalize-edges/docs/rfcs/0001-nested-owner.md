---
id: 0001-nested-owner
title: Nested component ownership
status: stable
rfc_state: accepted
affects:
  - auth
  - auth-routing
resolved_by: docs/decisions/0001-adr.md
required_updates: []
---

# RFC 0001: Nested component ownership

The bound symbol lives in a file two components could claim; the most-specific
claim decides the owner.

## Requirements

### Requirement: Route table
ID: route-table
Provenance: code

The auth router SHALL expose the login route.

#### Scenario: Login route
- **WHEN** the route table is built
- **THEN** the login route is present

## Resolution

Approved; see [ADR-0001](../decisions/0001-adr.md).
