---
id: 0001-accepted-good
title: Accepted RFC with declared scope
audience: explanation
tier: 2
status: stable
rfc_state: accepted
affects:
  - auth
resolved_by: docs/50-decisions/0001-adr.md
required_updates: []
---

# RFC 0001: Accepted, declared scope

Adds SSO login to the auth component.

## Requirements

### Requirement: SSO login
ID: sso-login
Provenance: code

Users SHALL be able to authenticate through their company identity provider.

#### Scenario: Valid SSO assertion
- **WHEN** the identity provider returns a valid assertion
- **THEN** a session is established

#### Scenario: Expired SSO assertion
- **WHEN** the identity provider returns an expired assertion
- **THEN** authentication is rejected

## Tasks

- `T1` Wire the identity-provider client. (req: sso-login)
- `T2` Add expired-assertion coverage. (req: sso-login)
- `T3` Refresh the auth component doc. (component: auth)

## Resolution

Approved for implementation; see
[ADR-0001](../../50-decisions/0001-adr.md).
