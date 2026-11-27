---
id: loans
title: Loans
status: stable
summary: The fee a late loan costs and the desk that lends.
describes:
  - src/lib.rs
  - src/loans/**
depends_on:
  - util
owns_tests:
  - tests/fees.rs
---

# Loans

A desk is opened with `Desk::new()`, and a late payment is charged fifty cents a day past its due day. [How a late payment is charged](../guides/lending.md) gives the rule in full.

## Scope & Limitations

The desk keeps nothing between runs.
