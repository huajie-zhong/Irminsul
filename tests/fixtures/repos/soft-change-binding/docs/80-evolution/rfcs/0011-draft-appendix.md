---
id: 0011-draft-appendix
title: Draft RFC with an appendix after the requirements
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects: []
---

# RFC 0011: Appendix

## Requirements

### Requirement: Rate limit
ID: rate-limit
Provenance: code

The API MUST reject requests above the configured rate.

#### Scenario: Over the limit
- **WHEN** a client exceeds the configured rate
- **THEN** the request is rejected

#### Scenario: Under the limit
- **WHEN** a client stays under the configured rate
- **THEN** the request is served

# Appendix

Prior wording, kept for the record; it is not part of the contract.

### Requirement: Stray
ID: stray

The system did other things.
