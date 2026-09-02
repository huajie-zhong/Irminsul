---
id: 0001-retire-publish
title: "ADR-0001: Retire the publish command"
audience: adr
tier: 2
status: stable
describes: []
retires:
  - id: publish-command
    kind: cli-command
    surface_identity: publish
    matches:
      - demo publish
    guidance: Use the release workflow instead.
---

# ADR-0001: Retire the publish command

## Status

Accepted.

## Context

The local publish command bypassed the release workflow.

## Decision

Remove `demo publish` and route releases through CI.

## Alternatives Considered

- Keep both paths. Rejected because they can publish different artifacts.

## Consequences

Release publication has one governed path.
