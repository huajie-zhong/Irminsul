---
id: usage
title: Using the ledger
status: stable
summary: The commands that print what the ledger holds.
describes: []
---

# Using the ledger

`ledger list` prints every amount, oldest first.

`ledger report` prints the total of every amount.

Pass `--limit` to print only the newest amounts.

Pass `--plain` for the bare number.

Set `LEDGER_DATE_FORMAT` to change how a day is printed.

`src/ledger/core.py` holds the ledger itself.

An agent calls `ledger_total` for the sum.

An agent calls `ledger_count` for how many amounts there are.

A shop enters each sale as it happens, and the [ledger component](../components/ledger.md)
says what keeps the sales in order.
