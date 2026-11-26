---
id: ledger
title: Ledger
status: stable
summary: Amounts kept in the order they were entered, and the commands that print them.
describes:
  - src/ledger/*.py
recommended_tests:
  - tests/test_ledger.py
---

# Ledger

The ledger keeps amounts in cents. [Using the ledger](../guides/usage.md) shows the commands.

`Ledger.add` enters an amount after every amount already there.

`Ledger.remove` drops one amount and keeps the others in order.

`Ledger.total` adds every amount up.

`parse_amount()` reads an amount written with a decimal point.

## Scope & Limitations

The ledger keeps nothing between runs.
