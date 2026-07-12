---
id: 0002-draft-ready
title: Draft RFC with declared scope
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects:
  - auth
---

# RFC 0002: Draft, declared scope

Adds step-up authentication to the auth component.

## Requirements

### Requirement: Step-up authentication
ID: step-up
Provenance: code

The system SHALL re-challenge a user before a sensitive action.

#### Scenario: Sensitive action
- **WHEN** a user starts a sensitive action
- **THEN** a second factor is requested

#### Scenario: Recent challenge
- **WHEN** the user passed a second factor moments ago
- **THEN** no further challenge is requested
