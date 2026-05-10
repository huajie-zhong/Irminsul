---
id: 0008-check-profiles-and-warning-policy
title: Check profiles and warning policy
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0008: Check profiles and warning policy

## Summary

Replace ambiguous check scope language with explicit profiles across
`irminsul check` and `irminsul fix`. The previous `--scope` wording mixed
selection mechanics with policy; profiles name the policy being applied.

This RFC is a clean breaking change. It removes `--scope` from both commands
and removes `--llm` from `irminsul check`.

## Motivation

Dogfooding exposed a confusing failure mode: the old default check command and
`--scope hard` could pass while `--scope all` surfaced many warnings. That was
not wrong behavior, but "all" suggested broader coverage than the CLI actually
provided.

The old interface created two problems for humans and agents:

1. They could assume all implemented checks ran when only configured checks ran.
2. They could assume strict mode enabled warnings, when it only changed the exit
   code for warnings already emitted.

`irminsul fix` used the same scope vocabulary, so it should move to the same
profile vocabulary at the same time.

## Detailed Design

### Profiles

Add a `--profile` option to `irminsul check` and `irminsul fix`.

| Profile | `check` behavior | `fix` behavior |
|---|---|---|
| `hard` | Run configured hard checks only. | Run configured hard checks and apply fixes only if selected checks expose them. |
| `configured` | Run configured hard and configured soft deterministic checks. | Apply fixes from configured deterministic checks that expose them. |
| `advisory` | Run configured hard, configured soft deterministic, and configured LLM checks. | Same deterministic fix behavior as `configured`; LLM checks are not used for mutation. |
| `all-available` | Run every implemented deterministic check, regardless of config. | Apply fixes from every implemented deterministic check that exposes them. |

`irminsul check` defaults to `--profile hard`.

`irminsul fix` defaults to `--profile configured`, because its purpose is
deterministic remediation rather than PR-gate enforcement.

### LLM policy

`advisory` implies configured LLM checks. There is no separate `--llm` selection
flag.

LLM execution still respects availability, budget, cache behavior, and
`required_in_ci` policy:

- If no API key is available and `required_in_ci = false`, configured LLM checks
  emit info findings saying they were skipped.
- If no API key is available and `required_in_ci = true`, the run emits an error.
- `--llm-budget` remains available to override the per-run cost ceiling.

### External link policy

`all-available` selects the implemented `external-links` check, but it does not
force network access. The check still respects `[checks.external_links].enabled`.

### Strict mode

`--strict` is exit-code policy only:

- Without `--strict`, error findings fail and warning findings do not.
- With `--strict`, error or warning findings fail.
- `--strict` does not enable soft checks, LLM checks, external link checks, or
  unavailable checks.

## Recommended CI Policy

- Pull request gate: `irminsul check --profile hard`
- Dogfood or nightly audit: `irminsul check --profile configured --strict`
- Optional semantic audit: `irminsul check --profile advisory --strict`
- Manual full deterministic inventory: `irminsul check --profile all-available`

## Implementation Plan

1. Add a shared `Profile` enum and map each profile to concrete check selection.
2. Remove `--scope` from `irminsul check` and `irminsul fix`.
3. Remove `--llm`; use `--profile advisory` for LLM checks.
4. Update the GitHub Action input from `scope`/`llm` to `profile`.
5. Update docs and init templates to use profiles.
6. Add tests for exit codes, rejected old flags, check selection, fix selection,
   strict mode, and JSON output.

## Drawbacks

This is a breaking CLI and action-input change. The break is intentional: a
temporary compatibility layer would preserve the ambiguous vocabulary this RFC
exists to remove.

## Alternatives

- Keep `--scope` as a deprecated alias. Rejected because it keeps the old mental
  model alive.
- Make `--scope all` run every implemented check. Rejected because it changes
  behavior while retaining the misleading option name.
- Keep `--llm` as an additional selector. Rejected because `advisory` should own
  LLM inclusion.
