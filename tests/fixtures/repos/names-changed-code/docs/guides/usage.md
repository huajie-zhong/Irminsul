---
id: usage
title: Using the ledger
status: stable
summary: The commands that print what the ledger holds.
describes: []
---

# Using the ledger

`ledger list` prints every amount, oldest first.

Run `ledger list` again after a sale to see it entered.

Set `LEDGER_DATE_FORMAT` to change how a day is printed.

`src/ledger/core.py` holds the ledger itself.

`late_fee()` charges fifty cents for each day a payment is late.

`due_day()` gives a payment thirty days.

An agent calls `ledger_total` for the sum.

A shop enters each sale as it happens, and the [ledger component](../components/ledger.md)
says what keeps the sales in order.

[The ledger's options](options.md) lists what the commands take.
