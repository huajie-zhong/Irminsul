---
id: overview
title: Overview
status: stable
summary: How the desk and the loan rules fit together.
describes: []
claims:
  - id: a-return-is-never-refused
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Taking a book back never fails, however late the book is.
    evidence:
      - src/loans/desk.py
    pinned:
      src/loans/desk.py: sha256:dbb4e60c52ec
---

# Overview

The [desk](../components/loans.md) keeps no state between calls: a loan is a value its caller holds.

Taking a book back always succeeds. <!-- claim:a-return-is-never-refused -->
