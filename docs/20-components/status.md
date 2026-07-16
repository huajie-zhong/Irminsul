---
id: status
title: Status command
audience: explanation
tier: 3
status: stable
summary: One-glance digest of docs inventory, source-file coverage, and findings.
depends_on:
  - checks
  - config
  - docgraph
describes:
  - src/irminsul/status.py
tests:
  - tests/test_cli_status.py
---

# Status command

`irminsul status` is the human's one-glance digest of the doc system's health. It reports the docs inventory (totals by layer and by frontmatter status), source-file coverage, and a findings summary. `--format json` emits the same report with stable keys (`version: 1`) for scripts.

The headline is source-file coverage. Every file admitted by the configured source policy is counted, and a file is claimed when at least one doc's `describes:` glob matches it — the same inventory and claim resolution the [uniqueness check](checks.md) uses. The digest reports the claimed total, the percentage, and the top directories ranked by unclaimed-file count, so a brownfield adopter sees coverage debt that the green check run cannot: the uniqueness omission warning only fires inside directories that already contain a claimed file.

The findings summary runs the configured hard and soft deterministic checks — the same selection as the configured check profile — and reports counts by severity plus per-check counts.

## Scope & Limitations

The report is a digest, not a gate: the command always exits 0 and emits no findings of its own. Its totals honor the shared source policy but do not apply the additional omission-noise heuristics used by `irminsul list undocumented`, so its undocumented count can still be higher.
