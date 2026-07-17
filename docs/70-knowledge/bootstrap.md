---
id: bootstrap
title: Bootstrapping Checklist
audience: tutorial
tier: 3
status: stable
describes: []
tests:
  - tests/test_init.py
---

# Bootstrapping Checklist

To adopt this system on a new or existing codebase, in order:

- [ ] Install Irminsul and run `irminsul init` (or `irminsul init --fresh` before code exists)
- [ ] Run `irminsul orient` and read the generated [agent navigation manifest](../AGENTS.md)
- [ ] Replace the prompts in [`00-foundation/principles.md`](../00-foundation/principles.md) with the project's intent
- [ ] Describe the system boundary in [`10-architecture/overview.md`](../10-architecture/overview.md)
- [ ] Add component docs whose `describes` and `tests` fields claim the current source and tests
- [ ] Record consequential design choices with `irminsul new adr`
- [ ] Run `irminsul context <path>` before changing an owned source path
- [ ] Run `irminsul check --profile hard` and commit the scaffolded CI workflow
- [ ] Review `irminsul list undocumented`, then enable suitable soft checks as the baseline becomes trustworthy

You can start with the generated skeleton, foundation, architecture overview, and hard profile. Source-ownership mapping and advisory checks can be tightened incrementally as the repository is mapped.

## Scope & Limitations

This is a checklist, not a step-by-step tutorial with expected output at each stage. It does not cover ongoing maintenance, doc-quality improvement, or rollout to additional source languages after initial adoption.
