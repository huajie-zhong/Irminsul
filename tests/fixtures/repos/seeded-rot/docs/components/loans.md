---
id: loans
title: Loans
status: stable
summary: Lending a book, renewing a loan and fining a late return.
describes:
  - src/loans/*.py
recommended_tests:
  - tests/test_loans.py
claims:
  - id: a-renewal-restarts-the-loan
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: A renewed loan runs its full length from the day it is renewed, not from its old due day.
    evidence:
      - src/loans/desk.py
    pinned:
      src/loans/desk.py: sha256:dbb4e60c52ec
---

# Loans

The desk lends a book, renews a loan and takes a book back. [Lending a book](../guides/lending.md)
shows the calls, and the [overview](../architecture/overview.md) how the two modules fit together.

`can_renew()` allows a loan two renewals and refuses a third.

A late return is fined 25 cents a day, and the fine stops growing at 5 dollars.
<!-- anchor: src/loans/policy.py#late_fee @sha256:e3f316c27a69 -->

A loan runs for two weeks.

A book that comes back early or on its due day costs nothing.

Renewing starts the loan again from the day of the renewal. <!-- claim:a-renewal-restarts-the-loan -->

## Scope & Limitations

The desk keeps no record of which books are out, so it lends a book that is already lent.
