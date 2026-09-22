---
id: cli
title: CLI
status: stable
depends_on:
  - change
  - checks
  - config
  - context
  - docgraph
  - init
  - new-list-regen
  - refs
  - seed
describes:
  - src/irminsul/cli.py
  - src/irminsul/__init__.py
  - src/irminsul/__main__.py
owns_tests:
  - tests/test_cli.py
  - tests/test_cli_check.py
  - tests/test_cli_check_now.py
  - tests/test_cli_cochange.py
  - tests/test_cli_explain.py
  - tests/test_cli_format_github.py
recommended_tests:
  - tests/test_cli.py
  - tests/test_cli_check.py
  - tests/test_cli_check_now.py
  - tests/test_cli_cochange.py
  - tests/test_cli_context.py
  - tests/test_cli_explain.py
  - tests/test_cli_format_github.py
inventory:
  - kind: cli-options
    source: src/irminsul/cli.py
    explained_in: any
    foreign:
      - --detach
      - --find-renames
      - --name-only
      - --porcelain
  - kind: cli
    source: src/irminsul/cli.py
    complete: true
    items:
      - init
      - check
      - context
      - status
      - explain
    omit:
      - seed
      - orient
      - refs
      - fix
      - surface
      - anchors
      - mcp
      - change status
      - change verify
      - change transition
      - change graph
      - change finalize
      - change impact
      - new adr
      - new component
      - new rfc
      - list baseline
      - list orphans
      - list stale
      - list undocumented
      - list lifecycle
      - list review
      - regen agents-md
---

# CLI

The Typer app that backs both the `irminsul` and `irm` console scripts; `irminsul --version` prints the installed version. The exact command surface is derived on demand from the Typer app — run `irminsul surface cli`.

On Windows, both console-script entry points configure stdout and stderr as UTF-8 before invoking Typer, and turn off Click's wildcard expansion so a quoted glob such as `--describes "src/**"` arrives as written rather than as a list of matching files. This keeps Unicode help text and findings stable under legacy code pages without changing streams when the app is imported as a library or invoked through `CliRunner`.

Common command paths:

- `irminsul init` — scaffold a new codebase. Delegates to [`init`](init.md).
- `irminsul check` — build the [DocGraph](docgraph.md) and run checks selected by `--profile`. Exits 1 on any error finding. `--diff <base>` adds the [co-change and diff-integrity](checks.md) passes: a warning for every owning doc whose claimed source files changed in `<base>...HEAD` without it, and errors when the change weakens the gate that judges it; time findings are left out of such a run. `--delta` (or `--delta-base <rev>`, defaulting to `HEAD`) reports only findings introduced relative to a base rev, and exits 2 rather than pass vacuously when the working tree matches `HEAD` and no base was named — see the [baseline component](baseline.md#delta-mode-check-delta) for the mechanism.
- `irminsul context` — build the [DocGraph](docgraph.md) and delegate task-specific navigation lookup to [`context`](context.md). `--before-edit <path...>` and `--after-edit` expose the common stateless editing loop with bounded authored excerpts; `--include` expands or suppresses content categories, while the path, topic, and changed modes remain available as power tools.
- `irminsul status` — summarize document inventory, source ownership, and configured findings through the [`status`](status.md) report.
- `irminsul explain [code]` — print what a finding code means and how to fix it, taken from each check's `explanations`; with no code, or an unknown one, list every known code grouped by check.

Co-change accepts two spellings, and they fail differently on purpose. `--diff <base>` is an explicit opt-in gate: an unresolvable base ref exits 2 rather than passing silently, because a gate that cannot compute its diff is a gate that never fires. `--base-ref`/`--head-ref` predate it and degrade gracefully: an unresolvable ref (a shallow CI clone that never fetched the base sha, a tarball checkout with no history) prints a yellow warning on stderr and the run continues, reporting the rest of the findings normally. An empty value for any of the three is a malformed invocation and exits 2 either way.

`--source-diff <ref>` is a second axis rather than a fourth spelling: it names a base in a cross-repository source's *own* repository, for a gate running on a source-repository pull request, and it needs one of the three above as well, because the diff-aware passes run only when this repository has a range. It fails like `--diff` and for the same reason — a ref the source checkout cannot resolve exits 2, since a rule handed an empty change set passes everything. Two spellings, and they do not mix: a bare ref applies to every declared source and every one must resolve it, while `--source-diff <source>=<ref>` names one declared source and may be repeated. The second exists because one ref for all made the gate unusable as soon as two repositories spelled their default branch differently — a pull request in one supplied its ref, the other could not resolve it, and the run exited 2. A name that `paths.sources` does not declare exits rather than being ignored, because a selector nobody matches is a gate reading an empty change set. `--pin-adoption-sources` records that repository's adoption boundary and ends the run, like the other adoption-writing flags. See the [adoption record](adoption-record.md) for what each reaches, and [private docs](../guides/private-docs.md) for the workflow that passes them.

Findings print one per line, sorted by severity then path. Severity colors are red (error), yellow (warning), cyan (info). Paths are POSIX-normalized so output is stable across platforms.

`irminsul check --profile` accepts `enabled`, the default, which runs the checks in `checks.enabled`, and `all-available`, which runs every implemented check. `history-depth` runs under either, because it judges whether the checkout can answer the checks that were selected rather than judging the tree; `adoption-record` runs under either for the same kind of reason, judging whether the record the ownership rules honour can be trusted, and reporting nothing when neither of them was selected. Neither is this command's own: both come from the mandatory-pass set in `checks/pipeline.py` that every entry point shares, so `context`, the [MCP server](mcp-server.md) and the [change](change.md) lifecycle gates reach the same verdict about them that this command does. The exit code is 1 when a finding is an error, which a certain finding is; `--strict` also fails on hint and time findings. `--fail-on` adds classes to the certain findings that always fail, comma-separated from `certain`, `hint`, and `time`, and cannot be combined with `--strict`; naming only `time` does not stop a certain finding failing the run, because no invocation can turn that gate off; a nightly run passes `--fail-on time`, so it fails on what time made stale and leaves certain findings to the pull request that introduced them. A certain finding on a draft doc is reported as a warning and fails as a hint only when its code reports the doc as unfinished ([drafts excuse an unfinished doc](../decisions/drafts-excuse-an-unfinished-doc-not-a-wrong-one.md)). An info finding never fails a run.

The CLI is intentionally thin: every subcommand resolves config, builds a graph, calls into a registry of work, and prints. Logic lives in the modules it dispatches to.
<!-- anchor: src/irminsul/cli.py#check @sha256:5626ef6b19af -->


## Scope & Limitations

The CLI contains no domain logic; every subcommand dispatches to a dedicated module. It does not communicate with external services. Invocations share no state except files on disk that a user asked for or a check caches: the baseline written by `check --init-baseline` and shrunk by `check --update-baseline`, and the `external-links` result cache when that check is enabled.
