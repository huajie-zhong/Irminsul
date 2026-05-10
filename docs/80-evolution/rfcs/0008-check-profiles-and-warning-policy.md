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

Replace ambiguous check scope language with explicit check profiles. The current
`--scope all` wording is misleading because it runs hard checks plus configured
soft checks, not every implemented check. This proposal introduces profile names
that describe the policy being applied and documents exactly what `--strict`
does.

## Motivation

Dogfooding exposed a confusing failure mode: `irminsul check` and
`irminsul check --scope hard` can pass while `irminsul check --scope all`
surfaces many warnings. That is not wrong behavior, but the name "all" suggests
broader coverage than the CLI actually provides.

This creates two problems for humans and agents:

1. They may assume all implemented checks ran when only configured checks ran.
2. They may assume `--strict` enables warnings, when it only changes the exit
   code for warnings that have already been emitted.

## Detailed Design

### Profiles

Add a new `--profile` option to `irminsul check`.

| Profile | Behavior |
|---|---|
| `hard` | Run configured hard checks only. |
| `configured` | Run configured hard and configured soft deterministic checks. |
| `advisory` | Run configured hard, configured soft deterministic, and configured LLM checks. |
| `all-available` | Run every implemented deterministic check, regardless of config. |

The `advisory` profile still respects LLM availability, budget, and
`required_in_ci` policy.

### Compatibility

Keep `--scope` temporarily. `--scope all` remains an alias for `--profile
configured` and emits a deprecation note. `--scope hard` and `--scope soft`
remain accepted until the next major release.

### Strict Mode

Document `--strict` as exit-code policy only:

- Without `--strict`, error findings fail and warning findings do not.
- With `--strict`, error or warning findings fail.
- `--strict` does not enable soft checks, LLM checks, external link checks, or
  unavailable checks.

### Recommended CI Policy

Recommended defaults:

- Pull request gate: `irminsul check --profile hard`
- Dogfood or nightly audit: `irminsul check --profile configured --strict`
- Optional semantic audit: `irminsul check --profile advisory --strict`
- Manual full inventory: `irminsul check --profile all-available`

## Implementation Plan

1. Add a `Profile` enum to the CLI and map each profile to a concrete check
   selection policy.
2. Keep `--scope` as a deprecated compatibility option.
3. Update action inputs to accept `profile` while preserving `scope`.
4. Update docs and init templates to use `configured` instead of `all`.
5. Add tests for exit codes, deprecation notes, and check selection behavior.

## Drawbacks

This adds another CLI option while `--scope` still exists. The temporary overlap
is intentional so existing CI does not break.

## Alternatives

- Keep `--scope all` and document it more clearly. This is less disruptive but
  preserves the misleading name.
- Make `--scope all` run every implemented check. That changes existing
  behavior and could surprise projects that intentionally configured a smaller
  soft-check set.

## Unresolved Questions

- Should `all-available` include external link checks when network access is
  unavailable?
- Should `advisory` imply `--llm`, or should it require an explicit `--llm`
  until LLM policy is more mature?
