---
id: 0003-adr-provenance
title: Non-code provenance requirement
audience: explanation
tier: 2
status: stable
rfc_state: accepted
affects:
  - auth
resolved_by: docs/50-decisions/0001-adr.md
required_updates: []
---

# RFC 0003: Non-code provenance requirement

The requirement is backed by the decision record, not by a symbol.

## Requirements

### Requirement: Retention window
ID: retention-window
Provenance: adr

Sessions MUST expire after the retention window fixed by the decision record.

#### Scenario: Expired session
- **WHEN** the retention window has passed
- **THEN** the session is rejected

## Resolution

Approved; see [ADR-0001](../../50-decisions/0001-adr.md).
