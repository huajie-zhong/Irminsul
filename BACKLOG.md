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

### `naive-fence-toggles`

Ten modules decide whether a line sits inside a fenced code block by toggling on any line
opening with three backticks or tildes, rather than using `FenceTracker`
(`src/irminsul/docgraph_index.py:212`) — none of them reference it:
`checks/code_spans.py`, `checks/doc_reality.py`, `checks/duplicate_block.py`,
`checks/liar.py`, `checks/reality.py`, `checks/retired_references.py`,
`checks/schema_leak.py`, `checks/section_reference.py`, `anchors.py`,
`listing/review.py`.

A four-backtick fence quoting a three-backtick example — the only way to document the
anchor syntax — reads as live prose, so documenting the syntax raises a certain
`claim-anchor/missing-file` that no ignore comment can silence. Migrate all ten in one
change, or the codebase keeps two fence dialects.

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

### `python-anchor-cannot-bind-constant`

`_find_symbol` (`src/irminsul/anchors.py:76`) matches only
`ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef` at line 86, so `mod.py#LIMIT` is
`missing_symbol` while `mod.js#LIMIT` resolves. A certain error on a correct anchor, which
means thresholds, registries and regexes cannot be anchored in Python at all.

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

## Release setup

- **Tag `v0.3.0`.** The repository has no tags, so `hatch-vcs` has nothing to read and
  `irminsul --version` reports `0.0.0+unknown`.
- **`HOMEBREW_TAP_TOKEN`** as a repository secret; `.github/workflows/release.yml`
  dispatches the Homebrew tap update with it.
- **PyPI trusted publisher** pointed at this repository.

## Review debt

Cross-repository adoption (the `siblings` layout, declared sources, and the adoption
record's `{path, source}` bindings) shipped in v0.3.0 without a clean external review
round. Eleven findings were raised against it across two rounds and all eleven were valid,
four of them in code written the same day. Treat that surface as unsettled.
