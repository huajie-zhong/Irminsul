---
id: composer
title: Composer Component
audience: explanation
tier: 3
status: stable
owner: "@anson"
last_reviewed: 2026-05-07
describes:
  - app/composer.py
tests:
  - tests/test_composer.py
---

# Composer

The composer turns a request into a plan.

## Scope & Limitations

Does not handle scheduling or prioritization; those belong to the planner.
