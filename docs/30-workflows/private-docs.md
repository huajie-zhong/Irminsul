---
id: private-docs
title: Private docs for a public code repo
audience: explanation
tier: 3
status: stable
describes: []
tests:
  - tests/test_private_docs_siblings.py
  - tests/test_init_siblings.py
---

# Private docs for a public code repo

An open-source project can keep its Irminsul docs tree private. One layout
supports this — `siblings` — verified end to end by
[`test_private_docs_siblings.py`](../../tests/test_private_docs_siblings.py).
It is the only alternative to the default `same-repo` layout; see
[`ADR-0022`](../50-decisions/0022-reduce-supported-repository-topologies.md)
for why the two nested layouts that used to sit here were retired.

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
path, not a repo-relative one — `walk_source_files` cannot express them as
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
      - docs/20-components/core.md  # inside the docs repo
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
      - run: pip install irminsul
      - run: irminsul check --profile=hard
        working-directory: workspace/docs
```

A public code repo needs no credential on the second checkout. A private one
does — add a `token:` or `ssh-key:` to that step.

## Scope & Limitations

Git diff-based views inspect only the repository where Irminsul was invoked.
Run from the docs repo, they cannot see changes committed in the sibling code
repo. This applies to `context --changed` and to diff-aware `check` runs using
`--base-ref`/`--head-ref`, so do not use strict co-change enforcement as a
cross-repository gate. Review each repository's change set separately and use
mtime drift as the cross-repository signal.

For the same reason `check --delta` refuses this layout outright rather than
answering wrongly: `git worktree add` checks out tracked files only, so the base
checkout would omit the code repo and every finding over it would be reported as
new. Run `check` without `--delta`. See
[baseline](../20-components/baseline.md) for the mechanism; teaching `--delta`
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
