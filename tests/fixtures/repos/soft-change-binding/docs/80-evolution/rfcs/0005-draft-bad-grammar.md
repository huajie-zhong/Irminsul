---
id: 0005-draft-bad-grammar
title: Draft RFC with malformed requirements
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects: []
---

# RFC 0005: Bad grammar

Every grammar failure mode in one section.

## Requirements

### Requirement: No id or provenance

The system does things.

### Requirement: Bad id
ID: Bad_ID
Provenance: wizard

The system SHALL exist.

#### Scenario: Only when
- **WHEN** something happens

### Requirement: Dup one
ID: dup-a
Provenance: code

The system SHALL do a thing.

#### Scenario: Good
- **WHEN** x happens
- **THEN** y follows

### Requirement: Dup two
ID: dup-a
Provenance: code

The system MUST do the other thing.

#### Scenario: Good too
- **WHEN** x happens
- **THEN** z follows

## Tasks

- `T1` Implement the thing. (req: dup-a)
- `T1` Implement it again. (req: ghost-req)
- `T2` Touch a component nobody declared. (component: billing)
