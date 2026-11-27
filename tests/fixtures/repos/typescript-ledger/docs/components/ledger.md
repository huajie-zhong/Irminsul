---
id: ledger
title: Ledger
status: stable
summary: Late fees, and the ledger that records each entry it removes.
describes:
  - src/ledger/**
owns_tests:
  - tests/fees.test.ts
---

# Ledger

`Ledger.remove` takes an entry off the ledger and returns it with the owner's name.
[Using the ledger](../guides/usage.md) shows how a late payment is charged.

## Scope & Limitations

The ledger keeps no fee history, and it does not decide who may remove an entry.
