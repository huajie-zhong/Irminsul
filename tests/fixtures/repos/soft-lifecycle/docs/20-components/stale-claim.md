---
id: stale-claim
title: Doc with a planned claim citing an accepted RFC
audience: reference
tier: 3
status: stable
describes: []
claims:
  - id: should-be-implemented
    state: planned
    kind: feature
    claim: This feature is planned but cites an accepted RFC.
    evidence:
      - docs/80-evolution/rfcs/0001-good.md
---

# Stale Claim

This doc has a planned claim whose evidence cites RFC 0001, which is accepted.
The check should warn that the claim state is out of sync.
