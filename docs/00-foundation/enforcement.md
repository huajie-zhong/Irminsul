---
id: enforcement
title: Mechanical Enforcement
audience: explanation
tier: 2
status: stable
describes: []
claims:
  - id: hard-checks-enabled
    state: enabled
    kind: ci_gate
    claim: This repository runs Irminsul hard checks in CI and fails when they emit errors.
    evidence:
      - .github/workflows/ci.yml
      - irminsul.toml
      - src/irminsul/cli.py
  - id: soft-deterministic-available
    state: available
    kind: advisory_checks
    claim: Deterministic soft checks are implemented and can be enabled through check profiles or config.
    evidence:
      - src/irminsul/checks/doc_reality.py
      - docs/20-components/checks.md
  - id: precommit-external
    state: external
    kind: local_tooling
    claim: Local pre-commit behavior is provided through the external pre-commit framework.
    evidence:
      - .pre-commit-config.yaml
  - id: fix-remediation-available
    state: available
    kind: auto_fix
    claim: The fix command applies deterministic remediations supplied by supported checks.
    evidence:
      - src/irminsul/cli.py
      - src/irminsul/fix.py
      - docs/20-components/new-list-regen.md
  - id: source-deletion-reckoning-planned
    state: planned
    kind: ci_gate
    claim: Source-deletion reckoning is planned but not a current guarantee.
    evidence:
      - docs/80-evolution/rfcs/0005-systemic-doc-enforcement.md
  - id: health-dashboard-not-enabled
    state: enabled
    kind: generated_report
    claim: This repository has no enabled health-dashboard generation workflow.
    evidence:
      - .github/workflows/ci.yml
---

# Mechanical Enforcement

The point of the whole system is that you do not have to remember every rule. The tooling turns structural documentation rules into checks, and this repository's CI currently blocks hard-check violations by running `irminsul check --profile=hard`. <!-- claim:hard-checks-enabled -->

This technical layer provides the mechanical realization of [**The Harness Principle**](principles.md#strategic-assumptions).

## Two Tiers of Enforcement

Every check in this system falls into one of two categories:

- **Hard, deterministic, blocking.** CI fails when these checks emit errors. <!-- claim:hard-checks-enabled -->
- **Soft, deterministic, advisory.** These checks can warn about drift or suspicious structure without being part of the hard profile. <!-- claim:soft-deterministic-available -->

The boundary between hard and soft is principled, and everything is deterministic: build correctness must never depend on model judgment, and semantic review belongs to the coding agent consuming Irminsul, not to the tool. Checks are pure graph operations, set comparisons, regex, glob resolution, and git-log arithmetic. <!-- claim:hard-checks-enabled -->

| Tier | Examples |
|------|----------|
| Hard | Frontmatter validity, glob resolution, source ownership coverage uniqueness, internal link integrity, schema-leak detection |
| Soft, deterministic | Mtime drift, external link rot, stale-doc reaper, orphan detector, generated-reference drift, claim provenance, boundary, import-deps, phantom-layer, reality |

## The Change Triplet

Every PR should touch the right combination of three things: **code**, **tests**, and **docs**. The tooling can make missing documentation visible, but final judgment about whether a specific change needs prose still belongs to reviewers.

## Pre-commit Hooks (run locally before push)

Local pre-commit behavior is external tooling configured by this repo, not an Irminsul runtime guarantee. <!-- claim:precommit-external -->

- Ruff lint and format checks
- Mypy
- Pytest
- Irminsul dogfood checks, where configured by the hook file

## CI Pipeline (run on every PR)

This repository's CI runs Python linting, type checking, tests, and the hard Irminsul profile. The hard Irminsul step fails the workflow when any hard check emits an error. <!-- claim:hard-checks-enabled -->

Other checks are implemented or planned at different maturity levels. Deterministic soft checks are available through configured or all-available profiles. `irminsul fix` can apply the remediations that active checks explicitly supply; some rewrites remain held until `--confirm`. Source-deletion reckoning remains planned work. <!-- claim:soft-deterministic-available --> <!-- claim:fix-remediation-available --> <!-- claim:source-deletion-reckoning-planned -->

## Supersession Enforcement (the "Did Anyone Mark This Deprecated?" Problem)

The most insidious failure mode is silent replacement: someone writes `composer-v2.md` covering the same ground as `composer.md`, but forgets to mark the old doc deprecated. Now both exist, both look authoritative, and they slowly contradict each other. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->

Current deterministic checks reduce this risk by enforcing source-ownership uniqueness and supersession consistency. When a supersession finding has one unambiguous remediation, `irminsul fix` updates its frontmatter; potentially irreversible rewrites require `--confirm`. <!-- claim:hard-checks-enabled --> <!-- claim:fix-remediation-available -->

Source-deletion reckoning is also planned rather than currently enabled. A future implementation should make deleted source paths force an explicit documentation decision in the same PR. <!-- claim:source-deletion-reckoning-planned -->

The combination is the point. Hard checks prevent mechanically invalid documentation states, while check-supplied fixes repair supported failure modes without inventing intent. <!-- claim:hard-checks-enabled --> <!-- claim:fix-remediation-available -->

## The Health Dashboard

No health-dashboard generation workflow is currently enabled in this repository. Health is inspected through `status`, `check`, `context`, and the focused `list` reports. <!-- claim:health-dashboard-not-enabled --> <!-- claim:soft-deterministic-available -->
