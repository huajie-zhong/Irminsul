---
id: 0004-draft-ready
title: Draft RFC ready for a decision
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects:
  - auth
---

# RFC 0004: Draft, ready

A well-formed draft: scope declared, awaiting the human decision.

## Requirements

### Requirement: Password reset
ID: password-reset
Provenance: code

Users SHALL be able to reset a forgotten password by email.

#### Scenario: Known address
- **WHEN** a reset is requested for a registered address
- **THEN** a single-use reset link is sent

#### Scenario: Unknown address
- **WHEN** a reset is requested for an unregistered address
- **THEN** no account information is disclosed
