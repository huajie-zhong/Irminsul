---
id: dead-glob
title: Glob Points At Nothing
audience: explanation
tier: 3
status: stable
owner: "@anson"
last_reviewed: 2026-05-07
describes:
  - app/real.py
  - app/missing/*.py
  - lib/ghost.py
---

# Dead glob

Two of the three patterns above resolve to zero files.
