---
id: util
title: Util
status: stable
summary: The clamp the loans code shares.
describes:
  - src/util.rs
depends_on:
  - loans
recommended_tests:
  - tests/fees.rs
---

# Util

`clamp()` keeps a number between two bounds.

## Scope & Limitations

The clamp does not choose its bounds: each caller passes them.
