# AGENTS.md — agent entry point for Irminsul

Irminsul is a Python CLI (`irminsul`) and composite GitHub Action (`action.yml`) that
checks a `/docs` tree against its code in CI; every check is deterministic. This
repository dogfoods it: CI runs `irminsul check` on `docs/`, the live spec of the doc
system the tool enforces. The marked section below is the one `irminsul init` writes for
every adopter, and a test keeps it equal to the template.

<!-- irminsul:agents-start -->
## The agent loop

Work every change in this order. `irminsul orient` lists the commands; each takes
`--format json`.

1. At the start of a session, run `irminsul orient` and read
   [`docs/AGENTS.md`](docs/AGENTS.md), the map of the docs tree.
2. Before editing, run `irminsul context <path...>` for the files you intend to touch,
   or `irminsul context --topic <query>` while locating them, then read the owning docs
   it names and the decision records they link. It runs no checks, so it is fast and it
   is not a green light.
3. Make the change, with the doc updates **in the same commit** as the code they
   describe. When a sentence explains code — what it does, why it works this way, what
   it guarantees — name that code in a code span, anchor the paragraph to it, or declare
   it as a claim with evidence. A doc is re-asked about code only through those
   connections.
4. After editing, run `irminsul context --after-edit` for the findings your change
   introduced, and `irminsul list review --changed` to re-read each sentence you added
   or changed against the code it names. Both also queue the claims whose evidence you
   touched, in docs you may never have opened: read the doc and the decisions it links,
   and answer the question asked. The review queue is a reading list: fix a sentence
   that is wrong, and leave one you re-read and found right. Only a finding needs a
   recorded answer. On a branch with committed work, give both `--base-ref origin/<base>`.
5. Run `irminsul fix` for the deterministic remediations of mechanical findings.
6. Before committing, run `irminsul check` and the tests your change touches; it must
   exit 0.
7. Before opening the pull request, run `irminsul check --diff origin/<base>`, the run CI
   enforces. It adds `co-change` and `diff-integrity`, which judge the change rather than
   the tree and catch a weakened gate. It includes uncommitted work, so one run before
   committing shows what the commit will trigger. A `co-change` warning on a doc you
   re-read and found still right is answered by the commit trailer its suggestion
   prints, in the commit that carries the files, not by an edit that says nothing.

Report any warning you leave and any decision still open. Accepting or finalizing an RFC
is the user's decision; the [agent protocol](docs/guides/agent-protocol.md) says how to
act on a finding and how to change direction.

## Follow the foundation layer

The `foundation/` layer — principles, anti-patterns, and what the project will not do —
binds your choices, not just your prose. Follow it unless a principle is wrong for the
change at hand; then say so to the user and let them decide, rather than quietly working
around it. A principle you had to break is worth reporting even when the build is green.

## What a finding tells you

`irminsul explain <code>` says what a finding code means, and
[Acting on a finding](docs/guides/agent-protocol.md#acting-on-a-finding) what to do next.

- **A finding is right about its fact and silent about the meaning.** It reports
  something mechanical: this link resolves to nothing, this symbol is absent, no doc
  claims this file. Take that fact as true. Whether the prose is *correct* is what no
  check knows, so "the check is wrong" is almost never the answer.
- **A green run does not mean the docs are right.** It means nothing provable is broken.
- **A suggestion is a menu, not a ranking.** Several end "...or remove it", which is for
  when the thing really is gone — not a shortcut to clearing the finding.
- **When doc and code disagree, decide which is wrong before editing either.** A sentence
  describing what the code *should* do is a bug to report, not a doc to rewrite.

These clear a finding while making the tree less true, and none is a repair: deleting a
claim, anchor or `inventory:` entry; narrowing a `describes:` glob; setting `status:
draft`; an ignore comment as the first move or one without a real reason; running
`irminsul baseline init` without an `Irminsul-Reviewed` trailer that names the baseline; editing an
implemented RFC; re-pinning an anchor or a claim before re-reading it, or a whole doc
after re-reading one claim (`anchors --re-pin --doc <doc>` with `--claim <id>` or
`--anchor <path#symbol>` re-pins only what you named), or acknowledging a `co-change`
warning before re-reading the doc; removing a check from `checks.enabled` or from the
workflow; adding a path to the adoption record, which names what was already unowned on
the day of adoption and only ever shrinks; deleting that record, or adopting a second
time, to get the first record's allowance back.

## Harness notes

Every harness loads this file: Cursor and Codex read a root `AGENTS.md` natively, and
Claude Code reads `CLAUDE.md`, which imports it with `@AGENTS.md`; keep that import if <!-- irminsul:ignore code-references reason="an import directive of the harness, not a file path" -->
you replace that file with your own. `.mcp.json` registers Irminsul's read-only MCP
server; the harness runs the `irminsul` on its own PATH, so that install needs
`pip install 'irminsul[mcp]'`.
<!-- irminsul:agents-end -->

## Report what dogfooding teaches you

In this repository you are the first-hand user Irminsul is built for. Run the loop above
with `irminsul` itself rather than working around it, and tell the user in your report
what you ran into:

- **Missing:** something that would have helped and does not exist. Propose it, with the
  moment you needed it.
- **In the way:** a finding with no honest answer, a false positive, a slow or noisy
  step, or output you had to work around.
- **Unclear:** a command or finding you were not sure how to use, or where a doc,
  `--help` or a suggestion sent you wrong.

Name the command, the finding code or the doc, what you expected, and what happened.

## This repository

**Gates.** Every change passes `irminsul check` and `irminsul check --diff origin/main`,
both with `--fail-on hint,time`: a warning nobody can answer is a gap to report, not noise.
On a branch, every command that compares a change takes `--base-ref origin/main`.

**Setup and tests.** Python 3.12 or later: install with `py -3.12 -m pip install -e
".[dev]"` rather than a bare `python`, whose meaning depends on PATH.

```bash
pytest -q                                # parallel; -n0 runs serially, e.g. under a debugger
ruff check . && ruff format --check .
mypy                                     # strict, src/irminsul only
```

`pyproject.toml` sets `filterwarnings = ["error"]`: fix a warning's source rather than
suppress it. A test's repository is a fixture under `tests/fixtures/repos/<scenario>/`, a
miniature codebase named for what it exercises (a new check gets its failing and, where
there is one, its green case), or one built with the helpers in `tests/conftest.py`. Add a
helper there rather than a private copy, never build a `DocGraph` by hand, and date test
commits with fixed instants. CI runs Linux, macOS and Windows, so paths go through
`pathlib` and are POSIX-normalized.

**Where to start reading.** [`overview.md`](docs/architecture/overview.md), then
[`check-pipeline.md`](docs/architecture/check-pipeline.md). A check receives only the
`DocGraph`, so ask first whether new behaviour belongs on the graph or in a check. The
Action installs the CLI and calls it; logic belongs in the CLI.

**The docs obey the rules they ship.** A doc change that breaks a rule breaks the build,
and then the doc is wrong, not the check: fix the frontmatter, glob or link.
[`CONTRIBUTING.md`](docs/CONTRIBUTING.md) is the authoring guide; read
[`layers.md`](docs/architecture/layers.md) before adding or moving a doc. This file sits
outside `paths.docs_root`, so only the checks that read `paths.extra_docs` see it.

**Versioning.** `hatch-vcs` derives the version from git tags; never hand-edit one.
`.github/workflows/release.yml` publishes a tag.

## Harness notes for this repository

A running MCP server imported its code once, so after irminsul's files change it refuses
every tool call, naming them. Reconnect it (`/mcp`, then reconnect `irminsul`), and until
then run the query through the CLI, such as `irminsul orient --format json`. For a closed
connection, [Wiring it into an agent](docs/components/mcp-server.md#wiring-it-into-an-agent)
tells its two causes apart and gives the repair.
