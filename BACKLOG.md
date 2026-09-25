# Backlog

What we intend to fix next. Every entry below was re-checked against this tree on
2026-09-24 before being written down, because the longer list this replaces had entries
that the v0.3.0 work closed without the list noticing.

This file sits outside `docs_root` on purpose: a backlog names things that do not exist
yet, which the docs tree is checked against. A longer historical list, including the
doc-versus-code mismatches, is kept outside this repository.

**Name an issue by its slug, never by a bare number.** Verify an entry against the code
before working it.

## Enforcement and correctness

### `ignore-audit-blind-to-unran-passes`

`cli.check` calls `pipeline.finish` (`src/irminsul/checks/pipeline.py:146`) three times —
`src/irminsul/cli.py:1482`, `:1499`, and `:1169` for `run_check` — each with fresh comment
objects, and only the call carrying `ran=names` audits. So whether a comment was used
never travels between passes: a comment naming only `co-change`, `diff-integrity`,
`history-depth` or `ignore-comment` can never be reported unused, and adding any
unregistered name exempts a whole comment.

Not a one-liner. Adding those names to `ran` makes an ordinary `irminsul check` report
valid diff-only comments as certain `ignore-comment/unused`, because `co-change` never
ran. A fix has to settle: one audit per invocation after the last pass that will run;
`ran` as the passes that actually ran; use accumulated across passes; what suppressing a
finding that carries no line even means; and whether `run_check` callers audit at all.

### `delta-not-scored-in-gate-strength`

`_gate_strength` (`src/irminsul/checks/diff_integrity.py:1131`) measures `--strict`,
`--fail-on`, `--diff`, `--base-ref` and `--profile`, but not `--delta`, which stops
pre-existing errors from failing the run. Adding it to a gate step scores identically to
not adding it.

The louder half of this is already closed and should not be re-reported: a step switched
off with `continue-on-error: true` or a statically false `if:` stops counting via
`_switched_off` (`:1179`), and `irminsul check || true` via `_neutralised` (`:1202`).

### `claim-move-and-reword-across-docs`

Within one document a surviving claim id is now matched on its own
(`src/irminsul/checks/diff_integrity.py:837`) and a reworded claim reports
`claim-reworded`. Across documents `kept_claims` (`:829`) still keys on `(id, text)`, so a
claim moved to another document *and* reworded in the same change reads as removed —
certain `governing-claim-removed` for a claim that exists one file over.

## Release pipeline

v0.3.0 was tagged and published on 2026-09-25. The tag, the `HOMEBREW_TAP_TOKEN` secret and
the PyPI trusted publisher are in place, and PyPI carries the wheel and sdist with
provenance attestations. Two jobs in `.github/workflows/release.yml` are not fine.

### `ghcr-package-stranded-by-the-rename`

`Push image to ghcr.io` failed with `denied: permission_denied: write_package` even though
the job declares `packages: write`. The package was created by this project's previous
repository, which has since been renamed, and a ghcr package's Actions access is bound to a
repository by **id** — so the package stayed with the renamed repository while the name
moved here.

The contrast with PyPI is the lesson. A trusted publisher matches on the repository *name*,
so the same rename handed publish rights to whatever repository inherited the name, and that
job succeeded without being reconfigured. One identity is a string, the other a number, and
a rename moves only the string.

Fix by hand: grant this repository Write on the existing package under Manage Actions
access, or delete the package and let this repository create it, then re-run the failed job.
Nothing in the workflow can detect the condition, so it cannot be fixed in the workflow.

### `homebrew-dispatch-reports-success-for-nothing`

`Bump Homebrew tap` reports success when the `repository_dispatch` call is *accepted*, which
is not the same as a formula being updated. The tap repository is **empty** — no branch, no
formula, nothing listening for `irminsul-release` — so the event has gone nowhere since
v0.1.0 while every release recorded a green Homebrew job. Either populate the tap with a
workflow on that event type, or drop the job. A step that cannot fail is worse than no step,
because it reads as coverage.

- The workflow creates no GitHub Release object for a tag.

## Review debt

Cross-repository adoption (the `siblings` layout, declared sources, and the adoption
record's `{path, source}` bindings) shipped in v0.3.0 without a clean external review
round. Eleven findings were raised against it across two rounds and all eleven were valid,
four of them in code written the same day. Treat that surface as unsettled.
