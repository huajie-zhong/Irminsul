---
id: private-docs
title: Private docs for a public code repo
status: stable
summary: Keeping the docs tree private beside an open-source code repo.
describes: []
owns_tests:
  - tests/test_private_docs_siblings.py
recommended_tests:
  - tests/test_init_siblings.py
  - tests/test_private_docs_siblings.py
---

# Private docs for a public code repo

An open-source project can keep its Irminsul docs tree private with the `siblings`
layout, verified end to end by
[`test_private_docs_siblings.py`](../../tests/test_private_docs_siblings.py).
It is the only alternative to the default `same-repo` layout;
[Init adopts in two layouts, and seed fills two docs](../decisions/init-adopts-in-two-layouts-and-seed-fills-two-docs.md)
records why no nested layout is supported.

`same-repo` is the default because one repository makes review of code, tests and
docs atomic, with shared history and direct filesystem access for the ownership
checks. Public code with private docs is the case for `siblings`, when API
stability outranks community participation.

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

Scaffold it from inside the docs repo with
`irminsul init --topology siblings --code-repo owner/code`. The
[init](../components/init.md) doc covers detection, and `parse_code_repo` in
`src/irminsul/init/command.py` documents which spellings `--code-repo` accepts.
The code repo does not have to exist yet; the source walk warns about its missing
root until the clone lands.

## Path semantics

Source files outside the docs repo carry a **source-root-relative** display
path, because `walk_configured_source_files` cannot express them as repo-relative.
With `source_roots = ["../code/src"]`, the file
`workspace/code/src/core.py` is addressed as `core.py`: <!-- irminsul:ignore code-references reason="a path in the example sibling checkout, not a file of this repository" -->

```yaml
describes:
  - core.py
```

Widen the root to `../code` if you prefer claims that read `src/core.py`. Files
inside the docs repo stay repo-relative. A spelling the source walk emits always
means the walked file, so a docs-repo file of the same short name that no root
covers is shadowed by it, and `globs` reports the collision so the root can be
narrowed.

`owns_tests:` reads that spelling too, resolved through the root that produced it:
with `test_roots = ["../code/tests"]`, the file
`workspace/code/tests/test_core.py` is owned as `test_core.py`. <!-- irminsul:ignore code-references reason="a path in the example sibling checkout, not a file of this repository" -->
A declared test root is *closed*, as a local one is: every file under it needs an
owner, so `../code/tests/helpers.py` needs `owns_tests:` too even though its name is <!-- irminsul:ignore code-references reason="a path in the example sibling checkout, not a file of this repository" -->
not test-shaped, and `test-ownership/unowned-test` says so until a doc claims it.
The two ownership rules partition the managed files, so `list undocumented` does
not list it.

The structured `claims:` field reads the same spelling. Evidence in the code repo
is source-root-relative, evidence inside the docs repo stays repo-relative, and an
absolute path or one that reaches out through `..` is an error: there is one
spelling, so no escape hatch.

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

## CI

The gate runs in the private docs repo, and CI has to rebuild the workspace
before it can run. `irminsul init --topology siblings` generates a workflow that
checks out both repositories under one parent with explicit `path:` arguments and
points the Action's `path` input at the docs checkout, so `source_roots` resolve
exactly as they do locally. <!-- anchor: src/irminsul/config.py#Paths.source_roots @sha256:303b4495d070 --> A public code repo needs no credential on the second
checkout; a private one needs a `token:` or `ssh-key:` on that step. The template
is `src/irminsul/init/workflows/siblings/docs-pr.yml.j2`.

### The code repo needs a gate of its own

That workflow fires on the docs repo's pull requests. The two repositories have
separate histories, so a pull request in the code repo makes no diff here and
starts nothing here: without a second workflow, a code change is judged by nothing
until somebody happens to open a docs pull request.

`irminsul init --topology siblings` writes that second workflow to
`.github/for-code-repo/code-pr.yml`, not to `.github/workflows/`, where this repo's <!-- irminsul:ignore code-references reason="a workflow irminsul init writes into the target repository, not one of this repository" -->
CI would run it against a code checkout nothing is reviewing. **Copy it into
`.github/workflows/` in the code repo and commit it there**; init runs here and
cannot commit there.

It runs the gate on the docs checkout with two ranges. `diff: HEAD` is the docs
repo's uncommitted work, which a clean checkout lacks, so that range is empty on
purpose. `source-diff` is the pull request's own range, resolved in each
cross-repo source root's own repository, and it reaches exactly one rule,
`diff-integrity/adoption-debt-touched`: editing recorded ownership debt means
documenting it in the same change. Everything else the gate reports about source
files, such as a new file with no owner, comes from walking the tree and needs no
range.

`--source-diff` is refused without a range in the docs repo too, because
`diff-integrity` runs only when this repo has one, and a ref the code checkout
cannot resolve exits 2. Both refuse rather than run on an empty change set, since a
gate that sees no changes passes everything.

Nothing seals that workflow the way `diff-integrity` seals the ones here: it lives
in the other repository, which this gate cannot read, so weakening it is a review
question rather than a finding.

### What Irminsul verifies, and what your settings do

On every run, and failing it, the `adoption-record` and `diff-integrity` checks
verify mechanically that the source roots are checked out and the record holds only
what was there at its pin, that the record has not grown or been rebound, and that
no gate file in this repository changed; `irminsul explain <code>` describes each
finding.

**Dependent on settings nothing here can read, set, or confirm.** Conflating these
with the above is how a repository comes to believe it is protected by a tool that
is only reporting.

- **That the docs-repo check is required.** Everything above is only a report until
  an administrator requires `check` — the job in `.github/workflows/docs-pr.yml` — on <!-- irminsul:ignore code-references reason="a workflow irminsul init writes into the target repository, not one of this repository" -->
  this repository's default branch. CI running and a merge being blocked are
  different things, and only the second is a gate.
- **That this repository's default branch is protected.** Validation is inductive:
  the adopting change is checked, and every later change is checked against the one
  before it. A record pushed straight to the default branch skips the only base case
  that chain has.
- **That the code repository runs `irminsul-docs-gate`, and requires it.** It
  reports only until that repository's settings require it; until then a code change
  that removes a doc's owner is caught when somebody next opens a docs pull request
  here, not when it is made. It needs a credential for a private docs repo, too.
- **That CI fetches enough history** for the pinned revision to be present
  (`fetch-depth: 0`). A shallow clone answers "not in this clone", honestly, and
  still fails the run.
- **That the ref a source declares is the branch you meant.** `init` writes
  `ref = "origin/main"`, remote-tracking, so it is what the remote had when the job
  fetched rather than a local branch anybody in the checkout can move; a fully
  qualified `refs/heads/...` would measure the boundary against a branch of that
  checkout. Changing it is reported (`diff-integrity/setting-weakened`), but
  **whether that branch is protected is not something this tool can see.** It checks
  only that a pin is contained in the ref's history; who may push to the branch, and
  who reviewed what reached it, are settings and reviews elsewhere.

### When the source repository is unavailable

Fail closed, out loud, and with the difference named. A root that is not checked out
is not "a tree with no files", which would read as a clean run; it is a tree that
cannot be read, and the finding says which root. The same holds for a pin the clone
does not contain. The tool will not conclude that a file does not exist because it
could not look, so the obligation that a first record name only paths the
configured walk produces is **not asked at all** while a root is missing: every
path under it would look absent, and the accusation would be wrong about every line.

## Upgrading a workspace that already ran `irminsul init`

Regenerating a template does not touch a workflow already committed. To add the
code repo's gate, run `irminsul init --topology siblings --code-repo <spec>` in a
scratch directory and copy `.github/for-code-repo/code-pr.yml` out of it. <!-- irminsul:ignore code-references reason="a workflow irminsul init writes into the target repository, not one of this repository" -->
`irminsul init --force` in the existing docs repo would also write the file, but it
rewrites every other scaffolded file it can reach; for one new file that is the
wrong instrument.

The Action's `path` input, which these workflows use, is new in 0.4.0: 0.3.0 and
earlier lack it, so a workflow they wrote installs the CLI with `pip` instead.

## Scope & Limitations

Git diff-based views inspect only the repository where Irminsul was invoked.
`--source-diff` supplies the sibling repo's range, but only to
`diff-integrity/adoption-debt-touched`; `context --after-edit`, `co-change` and the
rest of `diff-integrity` still see this repo alone. So strict co-change enforcement
is not a cross-repository gate: a source change whose doc was not updated is not
reported. Review each repository's change set separately, and use mtime drift as
the broader cross-repository signal.

`check --delta` refuses this layout outright rather than answering wrongly:
`git worktree add` checks out tracked files only, so the base checkout would omit
the code repo and every finding over it would be reported as new. Run `check`
without `--delta`. See [baseline](../components/baseline.md) for the mechanism.

A file in the sibling code repo answers to two spellings in commands that take a
path: its display spelling, so `irminsul context core.py` resolves with
`source_roots = ["../code/src"]`; and its filesystem path,
`irminsul context ../code/src/core.py`, which `context` maps to the display
spelling when the file exists under a configured root. Only the display spelling
may appear in the docs, and a path outside the docs repo and every configured root
exits 2.

Two repositories cannot be made atomic. Inside the docs repo, a doc change lands
with the change it describes; across the two repositories that stays a review
convention, not something CI can enforce.

Publishing any part of a private docs tree is a manual decision; nothing here
automates partial disclosure of individual docs.
