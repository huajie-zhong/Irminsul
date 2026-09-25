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

### `claim-move-and-reword-across-docs`

Within one document a surviving claim id is now matched on its own
(`src/irminsul/checks/diff_integrity.py:837`) and a reworded claim reports
`claim-reworded`. Across documents `kept_claims` (`:829`) still keys on `(id, text)`, so a
claim moved to another document *and* reworded in the same change reads as removed —
certain `governing-claim-removed` for a claim that exists one file over.

## Release pipeline

v0.3.0 was tagged and published on 2026-09-25: PyPI carries the wheel and sdist with
provenance attestations, and `ghcr.io/huajie-zhong/irminsul` carries `0.3.0` and `latest`.
The tag, the `HOMEBREW_TAP_TOKEN` secret and the PyPI trusted publisher are all in place.
One job in `.github/workflows/release.yml` still reports a success it has not earned.

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
