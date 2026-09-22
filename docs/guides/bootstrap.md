---
id: bootstrap
title: Bootstrapping Checklist
status: stable
describes: []
recommended_tests:
  - tests/test_init.py
---

# Bootstrapping Checklist

To adopt this system on a new or existing codebase, in order:

- [ ] Install Irminsul and run `irminsul init` (or `irminsul init --fresh` before code exists)
- [ ] Run `irminsul orient` and read the generated [agent navigation manifest](../AGENTS.md)
- [ ] Install the `mcp` extra (`pip install 'irminsul[mcp]'`) so the scaffolded `.mcp.json` resolves; if adoption left an existing registration untouched, wire the [MCP server](../components/mcp-server.md) by hand
- [ ] Replace the prompts in [`foundation/principles.md`](../foundation/principles.md) with the project's intent
- [ ] Describe the system boundary in [`architecture/overview.md`](../architecture/overview.md)
- [ ] Add component docs whose `describes` and `tests` fields claim the current source and tests
- [ ] Record consequential design choices with `irminsul new adr`
- [ ] Run `irminsul context <path>` before changing an owned source path
- [ ] Run `irminsul check` and commit the two scaffolded CI workflows
- [ ] Review `irminsul list undocumented`, and record existing certain findings in a baseline with `irminsul check --init-baseline` if they cannot be fixed yet

You can start with the generated skeleton, foundation, architecture overview, and every default check enabled. Source-ownership mapping can be tightened incrementally as the repository is mapped, while the baseline keeps old certain findings from blocking new work.

## Scope & Limitations

This is a checklist, not a step-by-step tutorial with expected output at each stage. It does not cover ongoing maintenance, doc-quality improvement, or rollout to additional source languages after initial adoption.
