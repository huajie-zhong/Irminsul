---
id: a-loan-is-renewed-at-most-twice
title: A loan is renewed at most twice
status: stable
summary: A loan may be renewed twice, so a book is back on the shelf within six weeks.
describes: []
governs:
  - src/loans/policy.py#can_renew
---

# A loan is renewed at most twice

## Status

Accepted, 2024-01-01.

## Context

A popular book that one reader renews without end never reaches the next reader.

## Decision

A loan is renewed at most twice, whoever asks.

## Alternatives Considered

No limit, which is what the waiting readers complained about.

## Consequences

A book is back on the shelf within six weeks of being lent.
