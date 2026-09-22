---
id: check-pipeline
title: Check Pipeline
status: stable
describes: []
---

# Check Pipeline

How `irminsul check` flows from CLI invocation to exit code.

## Steps

1. **Resolve config** — `find_config()` walks upward from the invocation directory until it finds `irminsul.toml`. When there is none, the built-in defaults apply and the run continues; a config that is not valid TOML or fails schema validation exits 2.

2. **Build the DocGraph** — `build_graph(repo_root, config)` walks `docs_root`, parses every `*.md`, and produces a `DocGraph` with nodes indexed by id and by repo-relative path. Parse failures and missing frontmatter are collected as sidebands, not exceptions.

3. **Select checks** — the `--profile` flag decides which checks run:
   - `enabled`, the default — the checks named in `checks.enabled`
   - `all-available` — every implemented check regardless of config

4. **Run checks** — each check receives the full `DocGraph` and returns a list of `Finding` records. Checks run sequentially; the graph is not mutated between checks.

5. **Apply classes and ignore comments** — each finding's code has a class. A certain finding is an error unless it sits on a draft doc *and* its code is one the check declares as reporting an unfinished doc ([drafts excuse an unfinished doc](../decisions/drafts-excuse-an-unfinished-doc-not-a-wrong-one.md)), a hint or time finding is never an error, and time findings are dropped given a diff range. A doc's `irminsul:ignore` comments then drop the hint and time findings they cover.

6. **Collect and sort findings** — all findings are merged and sorted by severity (errors first) then by path. With `--diff <base>` (or `--base-ref`/`--head-ref`) the `co-change` and `diff-integrity` passes add their findings and time findings are left out; a baseline file suppresses the findings it records; and `--delta` runs the checks again on the base revision and keeps only the new findings.

7. **Render output** — findings print one per line to stdout in `path:line  severity  [check/code]  message` format, with a suggestion line when the finding carries one. Severity colors: red (error), yellow (warning), cyan (info). `--format json` emits a versioned object instead, carrying the `findings` array, a `summary` of counts, and the `baseline` report. `--format github` emits GitHub Actions workflow commands (`::error file=…,line=…,title=…::message`) so each finding lands as an annotation on its own line in the pull-request diff, and still prints the summary line. The composite Action requests this format by default; its `format` input overrides it.

8. **Exit code** — exits 1 if any finding left after baseline and delta filtering has `severity == error`; exits 0 otherwise. The `--strict` flag also fails on warnings, which are hint and time findings, and `--fail-on <classes>` adds the listed classes to the certain findings that always fail. The exit code is identical for every output format, so the choice of format is presentational only.

## Scope & Limitations

This doc covers `irminsul check` only. The init, regen, and fix pipelines are not documented here.
