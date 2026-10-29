---
id: cli
title: CLI
status: stable
summary: CLI entry point.
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
  - user-errors
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
      - baseline init
      - baseline update
      - adoption init
      - adoption update
      - context
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
      - change finalize
      - new adr
      - new component
      - new rfc
      - list baseline
      - list undocumented
      - list lifecycle
      - list review
---

# CLI

The Typer app behind the `irminsul` console script; `irminsul --version` prints the installed version. The command surface is derived on demand: run `irminsul surface cli`, or ask a command for `--help`.

On Windows both console-script entry points set stdout and stderr to UTF-8 and turn off Click's wildcard expansion, so a quoted glob such as `--describes "src/**"` arrives as written. `main()` does both rather than the import, so using the app as a library or from a test runner leaves the streams alone.

A closed stdout is the end of the output, not a crash: when `head` or a pager closes the pipe, `main()` points stdout at the null device and exits 1 without a traceback. It is never 0, so a gate cut short cannot pass. POSIX raises `BrokenPipeError`; Windows raises an `OSError` whose code also means a bad argument elsewhere, so `main()` reads that code as a closed pipe only on Windows, and only for an error that names no file: one that does came from a command's own file work and is raised as before.

Where a command's reason is not in its `--help`:

- `irminsul check --diff <base>` is an explicit opt-in gate. A base that cannot be resolved, or an empty value, exits 2 rather than passing, because a gate that cannot compute its diff is a gate that never fires. The range, why uncommitted work counts and what `--committed-only` leaves out are in [A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md); `--source-diff` names a base in a cross-repository source's own repository, for which see the [adoption record](adoption-record.md) and [private docs](../guides/private-docs.md); `--delta` is the [baseline component](baseline.md#delta-mode-check---delta)'s.
- `irminsul baseline init`, `baseline update`, `adoption init` and `adoption update` rewrite a file, so each takes only `--path`: a partial run could not stand in for the whole run the baseline records ([One command per question, and one rule per flag](../decisions/one-command-per-question-and-one-rule-per-flag.md)).
- `irminsul context` packages what to read before an edit, or with `--after-edit` judges the change as `check --diff` does ([context](context.md)). `irminsul explain` prints a finding code's class and remedy from the `explanations` of its check.

A command that cannot proceed says so on stderr, exits with its status and writes nothing to stdout, so a consumer parsing `--format json` gets JSON or nothing. The modules the CLI dispatches to raise a [`UserError`](user-errors.md); `IrminsulGroup` in `cli.py` prints it in red and exits with its `code`, which is also what lets the MCP server call the same functions and report the error its own way. The same group answers a removed option with the one that replaced it. Which status means what is [One command per question, and one rule per flag](../decisions/one-command-per-question-and-one-rule-per-flag.md).

The CLI is meant to be thin: every subcommand resolves config, builds a graph, calls into the module that owns the rule, and prints. `check` asks `checks/pipeline.py` for its run through `run_checks`, for the `--delta` comparison through `run_delta` and for its exit code through `RunResult.failed`, and `adoption.assess` supplies what the adoption record leaves unreported; what stays in `cli.py` is resolving the flags and printing. The owners are [init](init.md), [checks](checks.md), [context](context.md), [change](change.md), [seed](seed.md), [refs](refs.md) and [new, list and fix](new-list-regen.md).
<!-- anchor: src/irminsul/cli.py#check @sha256:651b9650334c -->


## Scope & Limitations

The CLI holds no domain rule: what a finding is, how a change is judged and what a baseline hides are decided in the modules it dispatches to. It does carry orchestration of its own: flag validation, the re-pin sweep of `anchors`, the plan printing of `change`, and the ownership guard of `new component`. It does not communicate with external services. Invocations share no state except files on disk that a user asked for or a check caches: the baseline written by `irminsul baseline init` and shrunk by `irminsul baseline update`, and the `external-links` result cache when that check is enabled.
