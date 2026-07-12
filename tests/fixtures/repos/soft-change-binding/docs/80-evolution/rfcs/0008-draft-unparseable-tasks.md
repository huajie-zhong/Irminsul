---
id: 0008-draft-unparseable-tasks
title: Draft RFC whose task list has no ids
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects: []
---

# RFC 0008: Unparseable tasks

Every task bullet is written without a backticked id.

## Requirements

### Requirement: Plain login
ID: plain-login
Provenance: code

Users SHALL be able to log in.

#### Scenario: Valid password
- **WHEN** the password matches
- **THEN** a session is established

#### Scenario: Wrong password
- **WHEN** the password does not match
- **THEN** authentication is rejected

## Tasks

- T1 Wire the client. (req: plain-login)
- T2 Add coverage. (req: plain-login)
