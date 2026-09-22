---
id: baseline
title: Baseline ratchet
status: stable
summary: Brownfield adoption mechanism — a baseline file records existing certain findings so CI fails only on new ones; it is created once, only shrinks, and shows what it hides.
depends_on:
  - checks
describes:
  - src/irminsul/baseline.py
  - src/irminsul/delta.py
owns_tests:
  - tests/test_baseline.py
  - tests/test_cli_check_baseline.py
  - tests/test_cli_check_delta.py
  - tests/test_delta.py
  - tests/test_delta_identity.py
claims:
  - id: baseline-only-shrinks
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: A baseline records only certain findings and never grows — creation refuses to overwrite an existing file, and an update may only remove entries.
    evidence:
      - src/irminsul/baseline.py
---

# Baseline ratchet

Without a baseline, adopting Irminsul on an existing codebase would be all-or-nothing: every pre-existing violation would have to be fixed before CI could go green. The baseline is the escape hatch that does not become a loophole ([Baseline holds certain findings and only shrinks](../decisions/baseline-holds-certain-findings-and-only-shrinks.md)). Running `irminsul check --init-baseline` records the current certain findings in a baseline file (`.irminsul-baseline.json` by default, configurable as `paths.baseline`), and refuses when one already exists. While that file exists, [`check`](cli.md) hides exactly those findings — anything new still fails the build. Hint and time findings fail a run only when asked, through `--strict` or `--fail-on`, so the baseline neither records nor hides them.

## How matching works

A baselined finding is identified by the fingerprint of its check name, repo-relative POSIX path, and message. The line number and severity are deliberately excluded, so a finding that merely moves within a file stays suppressed, while one whose message changes (a different missing field, a different broken target) counts as new. Entries are stored sorted and human-readable, so baseline diffs are reviewable; stored fingerprints are recomputed on load rather than trusted.

Only certain findings are baselined, and a certain finding's message names the item it is about, such as a broken link's target, so an entry does not hide a different problem in the same doc. A test runs every check over the fixture corpus and fails when two certain findings in one doc share a message on different lines. Findings that audit a suppression — an unused ignore comment, a stale prose-file-reference marker, an [adoption record](adoption-record.md) that does not load or whose entries the boundary does not stand behind — are never baselined, so a baseline cannot hide an obsolete exception. Each check declares its own such codes, so a new one is excluded by being written rather than by being remembered here.

## The ratchet

The baseline only shrinks. `irminsul check --update-baseline` removes the entries that match nothing anymore; when a certain finding the file does not record is present, it prints that finding, writes nothing, and exits 1, so no command adds an entry to an existing baseline. In a pull request, `diff-integrity` reports a baseline file that gained entries by hand. The change that adopts Irminsul is the one exception: its merge base holds neither a config nor a baseline, so there is no ratchet yet and the first baseline is a creation. Without that, the pull request workflow [`init`](init.md) scaffolds would fail the very change that adds it.

What the baseline hides stays visible. Each run prints how many certain findings were hidden and how many entries are fixed. `--format github` adds a warning annotation to the pull request, and when `GITHUB_STEP_SUMMARY` is set it appends every hidden finding to the job summary. `irminsul list baseline` lists each entry as `hidden` or `fixed`. A run with `--no-baseline` shows the full picture on demand. In JSON output the report carries a `baseline` object (`applied`, `path`, `suppressed`, `stale`, and the `hidden` findings) so agents and CI dashboards can track the debt burning down.

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

When the base names the same tree as the working tree there is nothing to compare: every
finding is pre-existing, so the run would suppress all of them and exit 0 having checked
nothing — a green run for any tree, which is why such a run exits 2. The refusal compares
the trees rather than the flags, because `--delta-base HEAD`, and the sha `HEAD` resolves
to, name exactly the state the default does. It answers "what did my uncommitted edits
introduce?", and it is not the gate; plain `irminsul check` is.

The scratch worktree never touches the caller's working tree or index and is
removed unconditionally, with retry-then-`git worktree prune` fallback for
Windows's transient post-checkout file locks. `--delta` is an explicit opt-in
gate like `--diff`: an unresolvable `--delta-base` or a `--path` with no git
history exits 2 rather than silently reporting the full backlog. The exit code
reflects only the delta set — nonzero exactly when it contains an error (or,
under `--strict`, a warning). `--delta`, `--init-baseline`, `--update-baseline`, and `--no-baseline` are mutually
exclusive; plain baseline suppression is bypassed while `--delta` is active,
since the base-rev comparison already subsumes it for the common case
(`--delta-base` at or after the baseline was last written). In JSON output the
report carries a `delta` object (`applied`, `base`, `new`,
`pre_existing_suppressed`) alongside (not instead of) the normal `baseline`
object.

Because the scratch checkout is disposable, run-spanning check state must not be
anchored to it. `build_graph` takes a `state_root` alongside the root it walks:
equal to it for an ordinary run, and pinned to the caller's real repository for
the base pass. The `external-links` HTTP cache is the one such state today, so
both passes of a `--delta` run read and write a single cache. Anchoring it to
the walked root instead would make the base pass miss every entry, re-fetch
every external URL over the network, and then write the results into a scratch
directory about to be removed.

`--delta` works in the `same-repo` layout and refuses the `siblings` layout
rather than answering wrongly. `git worktree add` checks out tracked files
only, so the sibling code repo that `source_roots` reach through `../` is
simply absent from the base checkout (see
[private docs](../guides/private-docs.md)). The base run then finds
nothing under that tree and every finding over it survives as new — the exact
inversion of what `--delta` promises. `verify_single_repo_topology` compares
the nearest enclosing `.git` of each configured tree against the target repo's
own, and exits 2 naming the offending roots before any checkout happens.
`docs_root` is inspected alongside the source roots: no supported layout puts
it in its own repository, but a git submodule does, and it would be missing
from the base checkout the same way. Only configured trees are inspected, so a
vendored checkout carrying its own `.git` never trips it.

Teaching `--delta` to compare across the sibling boundary means anchoring the
doc walk and the source walk to different roots, and accepting that a single
`--delta-base` cannot name a point in a second repository's history — source
would have to be held constant across both passes. That design is open work,
proposed but not shipped. Until then the guidance matches the rest of the
diff-based views: run `check` without `--delta`, and use mtime drift as the
cross-repository signal.

## Scope & Limitations

The baseline applies to whatever profile was run when it was written and when it is applied; it stores findings, not profile state. It suppresses findings, not checks — a baselined check keeps running and keeps catching regressions elsewhere. A greenfield repo should never need one: this repo's own tree has no baseline file, and scaffolded repos do not get one.
