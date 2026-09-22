---
id: private-docs
title: Private docs for a public code repo
status: stable
describes: []
owns_tests:
  - tests/test_private_docs_siblings.py
recommended_tests:
  - tests/test_init_siblings.py
  - tests/test_private_docs_siblings.py
---

# Private docs for a public code repo

An open-source project can keep its Irminsul docs tree private. One layout
supports this — `siblings` — verified end to end by
[`test_private_docs_siblings.py`](../../tests/test_private_docs_siblings.py).
It is the only alternative to the default `same-repo` layout; see
[Adoption and repository layouts](../decisions/adoption-and-repository-layouts.md)
for why no nested layout is supported.

## The layout

A parent workspace directory holds two separate git repositories side by side:

```
workspace/
  code/     the public repo
  docs/     the private repo — holds irminsul.toml, docs/, and CI
```

Irminsul runs from the docs repo, which owns `irminsul.toml`:

```toml
[paths]
docs_root = "docs"
source_roots = ["../code/src"]
```

Neither repository is nested inside the other's working tree, so neither needs
a `.gitignore` rule to keep the other out of its history, and a collaborator
without access to the docs repo simply clones `code/` on its own.

Scaffold it with:

```bash
mkdir -p workspace/docs && cd workspace/docs
irminsul init --topology siblings --code-repo owner/code --language python
```

The code repo does not have to exist yet. When it is already checked out beside
the docs repo, init detects its languages and source roots, so `--language` may
be omitted. When it is not available locally, declare each intended language by
repeating `--language`; the scaffold writes `../<name>/src`, and the source walk
reports the missing root as a warning until the clone lands.

`--code-repo` takes either a GitHub coordinate or a path to the sibling.
`owner/repo`, `https://github.com/owner/repo` and `git@github.com:owner/repo.git`
all read as the coordinate `owner/repo`, which is what the generated workflow
checks out. Any other host, and any path — `../code`, `~/ws/code`, an absolute
path — configures the local layout and leaves the workflow's `repository:` as a
placeholder to fill in. Whatever the spelling, the code repo has to end up
beside the docs repo under one parent; anything else is refused rather than
scaffolded.

## Path semantics

Git-time lookups resolve through each file's nearest enclosing `.git`
([`mtime.py`](../../src/irminsul/git/mtime.py)), so doc commit times come from
the docs repo and source commit times from the code repo. That is what lets
mtime drift measure across the boundary.

Source files outside the docs repo carry a **source-root-relative** display
path, not a repo-relative one — `walk_configured_source_files` cannot express them as
repo-relative and does not try. With `source_roots = ["../code/src"]`, the file
`workspace/code/src/core.py` is addressed as `core.py`:

```yaml
describes:
  - core.py
```

Widen the configured root to `../code` if you prefer claims that read
`src/core.py`. Claims on files inside the docs repo — tests, fixtures, the docs
themselves — stay repo-relative as usual.

A spelling the source walk emits always means the walked file. If the docs repo
holds a file of the same short name that no root covers — its own readme beside
the code repo's, once the root is widened to `../code` — the shared spelling
names the code repo's file, and `globs` reports the collision so the root can
be narrowed.

`owns_tests:` reads that spelling too, and resolves it through the root that produced
it rather than against the docs repo. With `test_roots = ["../code/tests"]`, the
file `workspace/code/tests/test_core.py` is owned as:

```yaml
owns_tests:
  - test_core.py
```

A declared test root in the code repo is a *closed* root, exactly as a local one is:
every file under it needs an owner, including one whose name is not test-shaped.
`../code/tests/helpers.py` answers to `owns_tests:` rather than `describes:` —
declaring the root is the act of agreeing to that — so a doc has to claim it, and
`test-ownership/unowned-test` says so until one does. The two ownership rules
partition the managed files, so a file the test policy took is not also reported as
undocumented source, and `list undocumented` is the source listing rather than the
place to look for it.

The structured `claims:` field reads the same spelling. Evidence naming a file
in the code repo is written source-root-relative, exactly as `describes:` writes
it, and evidence naming anything inside the docs repo stays repo-relative:

```yaml
claims:
  - id: core-works
    state: implemented
    kind: feature
    claim: The core module exists.
    evidence:
      - core.py                     # ../code/src/core.py
      - docs/components/core.md  # inside the docs repo
```

There is one spelling, so there is no escape hatch: an evidence path that is
absolute, or that reaches out through `..`, is an error.

## CI

The gate runs in the private docs repo, and CI has to rebuild the workspace
before it can run: both repositories are checked out under one parent with
explicit `path:` arguments, and Irminsul runs from the docs checkout so
`source_roots` resolve exactly as they do locally. `irminsul init --topology
siblings` generates this; the composite Action cannot carry a
`working-directory`, so the workflow installs the CLI and calls it directly.

```yaml
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          path: workspace/docs
          fetch-depth: 0   # mtime drift needs full history
      - uses: actions/checkout@v4
        with:
          repository: owner/code
          path: workspace/code
          fetch-depth: 0   # mtime drift reads the code repo's own history
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "irminsul==0.3.0"
      - run: irminsul check --diff "origin/$BASE_REF"
        working-directory: workspace/docs
        env:
          BASE_REF: ${{ github.base_ref }}
```

A public code repo needs no credential on the second checkout. A private one
does — add a `token:` or `ssh-key:` to that step.

### The code repo needs a gate of its own

That workflow lives in the docs repo and fires on *its* pull requests. The two
repositories have separate histories, so a pull request in the code repo makes no
diff here and starts nothing here: without a second workflow, a code change is
judged by nothing until somebody happens to open a docs pull request.

`irminsul init --topology siblings` writes that second workflow to
`.github/for-code-repo/code-pr.yml` — beside the docs repo's own workflows and
deliberately not in `.github/workflows/`, where this repo's CI would run it
against a code checkout nothing is reviewing. **Copy it into `.github/workflows/`
in the code repo and commit it there**; init runs here and cannot commit there.

It checks out the code repo at the pull request's head and the docs repo at its
default branch, then runs the gate from the docs checkout with two ranges:

```bash
irminsul check --diff HEAD --source-diff "origin/$BASE_REF"
```

`--diff HEAD` is the docs repo compared with itself. Nothing is under review
there, so that range is empty on purpose — and it needs no knowledge of the docs
repo's default branch name. `--source-diff` is the range that matters: this pull
request's own, resolved in each cross-repo source root's own repository. It
reaches exactly one rule, `diff-integrity/adoption-debt-touched`, the one that
says editing recorded ownership debt means documenting it in the same change.
Everything else the gate reports about source files — a new file with no owner, an
entry the adoption record cannot account for — comes from walking the tree and
needs no range at all, which is why those already worked here and touch-to-own
did not.

`--source-diff` is refused without a range in the docs repo too, because
`diff-integrity` runs only when this repo has one, and a clean report from a run
that judged nothing is worse than a usage error. A ref the code checkout cannot
resolve exits 2 rather than reading an empty change set, for the same reason: a
gate that sees no changes passes everything.

Three things that workflow cannot install for you, because they are settings on
the code repo:

1. A **credential** for a private docs repo, as a secret the workflow reads.
2. **Branch protection** making the check required. Until it is, the workflow
   reports and does not gate — CI running and a merge being blocked are different
   things, and only the second is a gate.
3. Nothing seals that workflow the way `diff-integrity` seals the ones here. It
   lives in the other repository, which this gate cannot read, so weakening it is
   a review question rather than a finding.

### What Irminsul verifies, and what your settings do

Two columns, because conflating them is how a repository comes to believe it is
protected by a tool that is only reporting.

**Verified mechanically, on every run, and the run fails:**

| condition | finding |
|---|---|
| a configured source root is not checked out | `adoption-record/source-unverifiable` |
| the pinned revision is not in the source clone | `adoption-record/source-unverifiable` |
| a recorded entry was not in the source repo at the pin | `adoption-record/debt-not-at-source-revision` |
| the record does not load | `adoption-record/unreadable` |
| the record gains an entry, or a pin moves | `diff-integrity/adoption-record-grew`, `.../adoption-source-rebound` |
| a workflow *in this repository* is weakened | `diff-integrity/gate-weakened` |
| `--source-diff` names a ref the code checkout cannot resolve | exit 2, never an empty change set |

**Dependent on settings nothing here can read, set, or confirm:**

- **That the docs-repo check is required.** Every row above is a report until an
  administrator requires `check` — the job in `.github/workflows/docs-pr.yml` — on
  this repository's default branch. CI running and a merge being blocked are
  different things, and only the second is a gate.
- **That this repository's default branch is protected.** Validation is inductive:
  the adopting change is checked, and every later change is checked against the one
  before it. A record pushed straight to the default branch skips the only base case
  that chain has.
- **That the code repository runs `irminsul-docs-gate`, and requires it.** It is
  reporting-only by default, and you make it required in that repository's own
  settings. Until then a code change that removes a doc's owner is caught when
  somebody next opens a docs pull request here, not when it is made.
- **That CI fetches enough history** for the pinned revision to be present
  (`fetch-depth: 0`). A shallow clone answers "not in this clone", which is honest,
  and still fails the run.
- **That the ref a source declares is the branch you meant.** `init` writes
  `ref = "origin/main"` — remote-tracking, so it is what the remote had when the job
  fetched rather than a local branch anybody in the checkout can move. A fully
  qualified `refs/heads/...` is also accepted and is right for a local experiment;
  in CI it would measure the boundary against a branch of that checkout. Which one is
  configured is visible in the diff, and changing it is reported
  (`diff-integrity/setting-weakened`), but **whether that branch is protected is not
  something this tool can see.** It checks that a pin is contained in the ref's
  history. Who may push to the branch, and who reviewed what reached it, are settings
  and reviews elsewhere.

### Deleting a recorded file in the code repository

Editing recorded debt means documenting it, and the document lives here — a pull request in
the code repository cannot add one, but it can wait for one, so the gate there reports the
edit and the docs repository answers it.

**Deleting** one is different, and is exempt. The remedy for touching recorded debt is to
retire the entry in the same change, and the record is in *this* repository at its default
branch: a source-side pull request cannot change it, and retiring the entry here first fails
while the file still exists unowned. Requiring it would make such a deletion unmergeable once
that workflow is required — a gate nobody can pass rather than a gate. So a source-side
deletion leaves the entry stale, which this design tolerates everywhere, and the next
`check --update-adoption` here retires it. Re-creating the path is still caught, because the
file then exists and touching it is an edit.

### When the source repository is unavailable

Fail closed, out loud, and with the difference named. A root that is not checked out
is not "a tree with no files" — which would read as a clean run — it is a tree that
cannot be read, and the finding says which root and what to do about it. The same
holds for a pin the clone does not contain.

What the tool will not do is conclude that a file does not exist because it could not
look. The obligation that a first record name only paths the configured walk produces
is **not asked at all** while a configured root is missing: every path under that root
would look absent, and the accusation would be wrong about every line.

## Upgrading a workspace that already ran `irminsul init`

Regenerating a template does not touch a workflow already committed, and a record
written before the boundary existed does not gain one by itself. Two steps, both
one-time:

1. **Pin the adoption boundary.** A record naming files from the code repo with no
   `sources` entry now fails the run with
   `adoption-record/source-unverifiable`, because nothing establishes that
   those files pre-date adoption. Run `irminsul check --pin-adoption-sources` in
   the docs repo, check the revision it reports is the one you adopted at, and
   commit the record. The command only ever adds a pin; it will not move one, so
   running it twice is safe and the second run says so.
2. **Add the code repo's gate.** Run `irminsul init --topology siblings
   --code-repo <spec>` in a scratch directory and copy
   `.github/for-code-repo/code-pr.yml` out of it, or write it by hand from the
   snippet above. Then fill in the docs repo's coordinate, add the credential if
   the docs repo is private, and make the check required.

`irminsul init --force` in the existing docs repo would also write the file, but
it rewrites every other scaffolded file it can reach as well; for one new file
that is the wrong instrument.

## Scope & Limitations

Git diff-based views inspect only the repository where Irminsul was invoked, with
one exception: `--source-diff` supplies the sibling repo's range, and it reaches
`diff-integrity/adoption-debt-touched` and nothing else. Everything else that reads
a diff still sees this repo alone — `context --changed`, `co-change`, the rest of
`diff-integrity`, and diff-aware runs using `--base-ref`/`--head-ref`. So do not
use strict co-change enforcement as a cross-repository gate: a source change whose
doc was not updated is not reported. Review each repository's change set
separately, and use mtime drift as the broader cross-repository signal.

Teaching co-change across the boundary is deliberately not what `--source-diff`
did. It would change what an existing check means in one layout only, and what
that comparison should even be is still an open design, worked out in the draft
cross-repo delta proposal under `docs/rfcs/`.

For the same reason `check --delta` refuses this layout outright rather than
answering wrongly: `git worktree add` checks out tracked files only, so the base
checkout would omit the code repo and every finding over it would be reported as
new. Run `check` without `--delta`. See
[baseline](../components/baseline.md) for the mechanism; teaching `--delta`
to compare across the sibling boundary is proposed but not shipped.

Commands that take a path resolve it against the repository Irminsul was
invoked from. A file in the sibling code repo answers to two spellings there:
its display spelling — the source-root-relative form `describes:` and
`claims[].evidence` use, so with `source_roots = ["../code/src"]`,
`irminsul context core.py` resolves — and its filesystem path,
`irminsul context ../code/src/core.py`, which `context` maps to that same
display spelling when the file exists under a configured source root. The
display spelling is still the only form the docs themselves may use; a path
outside the docs repo and outside every configured root exits 2.

Two repositories cannot be made atomic. The Change Triplet holds inside the
docs repo; coordinating a code change with its doc change stays a review
convention, not something CI can enforce.

Publishing any part of a private docs tree is a manual decision; nothing here
automates partial disclosure of individual docs.
