---
id: 0009-draft-tilde-fence
title: Draft RFC with a tilde fence holding an unbalanced backtick fence
audience: explanation
tier: 2
status: draft
rfc_state: draft
affects:
  - auth
---

# RFC 0009: Tilde fence

A transcript block opens a backtick fence it never closes; the requirements
section that follows is still real.

## Design

~~~text
The session log pasted below opens a fence and never closes it:
```
~~~

## Requirements

### Requirement: Session timeout
ID: session-timeout
Provenance: code

Idle sessions MUST expire after thirty minutes.

#### Scenario: Idle session
- **WHEN** a session is idle for thirty minutes
- **THEN** the session is invalidated

#### Scenario: Active session
- **WHEN** a session sees activity
- **THEN** the timeout resets
