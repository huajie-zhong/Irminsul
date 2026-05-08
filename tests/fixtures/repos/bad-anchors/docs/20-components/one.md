---
id: one
title: One
audience: explanation
tier: 3
status: stable
owner: "@anson"
last_reviewed: 2026-05-08
---

# One

Same-doc anchor that exists: [section-one](#section-one). OK.

Same-doc anchor that doesn't: [missing](#nonexistent-section). Should fail.

Cross-doc anchor that exists: [two-sec](two.md#section-two). OK.

Cross-doc anchor that doesn't: [two-bad](two.md#nonexistent). Should fail.

## Section One

content
