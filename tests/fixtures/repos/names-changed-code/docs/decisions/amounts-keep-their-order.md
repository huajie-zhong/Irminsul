---
id: amounts-keep-their-order
title: Amounts keep their order
status: stable
summary: The ledger never reorders what was entered.
describes: []
---

# Amounts keep their order

## Status

Accepted, 2024-01-01.

## Context

A shop reads its ledger from the top, and `Ledger.remove` once left a gap behind.

## Decision

`Ledger.add` enters an amount last, and nothing reorders the amounts before it.

## Alternatives Considered

Sorting by amount, which hides the order of the day.

## Consequences

`Ledger.total` reads the amounts in any order.
