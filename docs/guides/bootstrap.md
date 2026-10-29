---
id: bootstrap
title: Bootstrapping Checklist
status: stable
summary: Adopting Irminsul, and the order of the first steps on an existing codebase.
describes: []
recommended_tests:
  - tests/test_init.py
---

# Bootstrapping Checklist

Install Irminsul and run `irminsul init` (or `irminsul init --fresh` before code exists), as the [README](../../README.md) Quickstart shows; `init` prints the next steps. On an existing codebase, their order matters:

- [ ] Run `irminsul adoption init` before writing the first component doc. It records the files that have no owning doc today, so they do not fail CI while you work through them; skip it on a new project or one whose code is already documented
- [ ] Add component docs whose `describes` and `owns_tests` fields claim the current source and tests
- [ ] Record other existing certain findings that cannot be fixed yet in a baseline with `irminsul baseline init`

The [adoption record](../components/adoption-record.md) and the [baseline](../components/baseline.md) keep old gaps and old certain findings from blocking new work.

## Scope & Limitations

This is a checklist, not a step-by-step tutorial with expected output at each stage. It does not cover ongoing maintenance, doc-quality improvement, or rollout to additional source languages after initial adoption.
