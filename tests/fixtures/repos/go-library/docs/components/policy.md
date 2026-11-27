---
id: policy
title: Policy
status: stable
summary: The fines a late loan costs.
describes:
  - internal/policy/**
depends_on:
  - desk
owns_tests:
  - internal/policy/policy_test.go
---

# Policy

The policy prices a loan that comes back late, one unit a day. The [lending guide](../guides/lending.md) states the rate in cents.

## Scope & Limitations

The policy does not decide who is charged: the desk asks it what a late loan costs.
