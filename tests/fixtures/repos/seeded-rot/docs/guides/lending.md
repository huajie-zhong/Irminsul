---
id: lending
title: Lending a book
status: stable
summary: How to lend a book and take it back.
describes: []
---

# Lending a book

Lend a book with `check_out()`, which returns a loan whose renewal count starts at zero.

A reader who brings a book back late never owes more than 5 dollars.

The fine for a late book stops growing once it reaches 5 dollars.
<!-- anchor: tests/test_loans.py#test_fee_is_capped @sha256:4d4c1db6725b -->
