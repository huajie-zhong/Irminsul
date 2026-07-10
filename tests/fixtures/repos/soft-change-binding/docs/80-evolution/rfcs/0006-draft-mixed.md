---
id: 0006-draft-mixed
title: Draft RFC mixing disposition with requirements
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects: []
---

# RFC 0006: Mixed

## Requirements

No new behavioral requirements: this refactor preserves the existing contract.

### Requirement: Contradiction
ID: contradiction
Provenance: code

The system SHALL contradict its own disposition.

#### Scenario: Both present
- **WHEN** the section declares both
- **THEN** the grammar check flags it
