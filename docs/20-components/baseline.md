---
id: baseline
title: Baseline ratchet
audience: explanation
tier: 3
status: stable
summary: Brownfield adoption mechanism — a baseline file grandfathers existing findings so CI fails only on new ones, and only ever shrinks.
depends_on:
  - checks
describes:
  - src/irminsul/baseline.py
  - src/irminsul/delta.py
tests:
  - tests/test_baseline.py
  - tests/test_cli_check_baseline.py
  - tests/test_delta.py
  - tests/test_cli_check_delta.py
---

# Baseline ratchet

Adopting Irminsul on an existing codebase used to be all-or-nothing: every pre-existing violation had to be fixed before CI could go green. The baseline is the escape hatch that does not become a loophole. Running `irminsul check --update-baseline` records the current error and warning findings in a baseline file (`.irminsul-baseline.json` by default, configurable as `paths.baseline`). While that file exists, [`check`](cli.md) suppresses exactly those findings — anything new still fails the build.

## How matching works

A baselined finding is identified by the fingerprint of its check name, repo-relative POSIX path, and message. The line number and severity are deliberately excluded, so a finding that merely moves within a file stays suppressed, while one whose message changes (a different missing field, a different broken target) counts as new. Entries are stored sorted and human-readable, so baseline diffs are reviewable; stored fingerprints are recomputed on load rather than trusted.

Info-level findings are never baselined: they do not affect exit codes, so recording them would only bloat the file.

## The ratchet

The baseline only shrinks. Each run reports how many entries are stale — present in the file but matching nothing anymore — and re-running with `--update-baseline` rewrites the file from what currently fires, dropping the paid-off debt. A run with `--no-baseline` shows the full unsuppressed picture on demand. In JSON output the report carries a `baseline` object (`applied`, `path`, `suppressed`, `stale`) so agents and CI dashboards can track the debt burning down.

## Delta mode (`check --delta`)

Where the baseline file grandfathers a repo's *entire* backlog once, `--delta`
answers a narrower, per-invocation question: which findings did *this* diff
introduce? `irminsul check --delta` (or `--delta-base <rev>`, which implies
`--delta` and defaults to `HEAD`) runs the same configured checks twice — once
against the live working tree, once against `<rev>` checked out into a scratch
`git worktree add --detach` under the system temp directory — and reports only
findings whose fingerprint is new. It reuses the exact fingerprint function
above (`irminsul.baseline.finding_fingerprint`), so "new" means the same thing
under `--delta` as it does under the ratchet.

The scratch worktree never touches the caller's working tree or index and is
removed unconditionally, with retry-then-`git worktree prune` fallback for
Windows's transient post-checkout file locks. `--delta` is an explicit opt-in
gate like `--diff`: an unresolvable `--delta-base` or a `--path` with no git
history exits 2 rather than silently reporting the full backlog. The exit code
reflects only the delta set — nonzero exactly when it contains an error (or,
under `--strict`, a warning). `--delta` and `--update-baseline` are mutually
exclusive; plain baseline suppression is bypassed while `--delta` is active,
since the base-rev comparison already subsumes it for the common case
(`--delta-base` at or after the baseline was last written). In JSON output the
report carries a `delta` object (`applied`, `base`, `new`,
`pre_existing_suppressed`) alongside (not instead of) the normal `baseline`
object.

Cross-repo topologies are a known limitation: a `source_roots` entry that
reaches outside the docs repo (Topology A's sibling code checkout) resolves
relative to the scratch worktree's temp location for the base-rev pass, not
the real sibling repo, so source-dependent checks over that root can differ
between the two passes. Same-repo topologies are unaffected.

## Scope & Limitations

The baseline applies to whatever profile was run when it was written and when it is applied; it stores findings, not profile state. It suppresses findings, not checks — a baselined check keeps running and keeps catching regressions elsewhere. A greenfield repo should never need one: this repo's own tree has no baseline file, and scaffolded repos do not get one.
