---
id: desk
title: Desk
status: stable
summary: The desk that lends items and posts each loan to the ledger.
describes:
  - internal/desk/**
depends_on:
  - policy
owns_tests:
  - internal/desk/desk_test.go
---

# Desk

`Desk.CheckOut` lends an item to a patron and posts the loan to the ledger.

## Scope & Limitations

The desk does not keep stock: an item must already be on the shelf before it is lent.
