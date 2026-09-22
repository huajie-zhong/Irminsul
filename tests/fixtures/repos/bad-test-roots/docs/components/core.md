---
id: core
title: Core
status: stable
describes:
  - src/core.py
owns_tests:
  - tests/test_core.py
---

# Core

Owns the one test beside it. `tests/fresh/` and `tests/nested/deeper/` hold tests that no
document names, in directories where nothing is owned — the case a rule that spread only
from an already-owned sibling could never reach.
