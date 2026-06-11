---
id: private-docs
title: Private docs for a public code repo
audience: explanation
tier: 3
status: stable
describes: []
tests:
  - tests/test_private_docs_topologies.py
---

# Private docs for a public code repo

An open-source project can keep its Irminsul docs tree private. Two layouts
support this, both verified end to end by
[`test_private_docs_topologies.py`](../../tests/test_private_docs_topologies.py);
git-time lookups resolve through the nearest enclosing `.git`
([`mtime.py`](../../src/irminsul/git/mtime.py)), which is what lets every
check work across a repository boundary.

## Topology A — the docs repo is primary

The private repo is the docs repo. The public code repo is cloned inside it
as a gitignored subfolder, and `paths.source_roots` points into it
(for example `code/src`). This is the layout that init-docs-only scaffolds.

- `.gitignore` in the docs repo contains `/code/` so the clone never leaks
  into the private history.
- `describes:` claims use the path through the subfolder
  (`code/src/module.py`), and the ownership, source-file coverage, and drift
  checks resolve them normally.
- CI runs in the private repo: check out the docs repo, clone the public code
  repo into the expected subfolder, then run `irminsul check`.

## Topology B — the code repo is primary

The public repo keeps its normal layout, and `docs/` is itself a separate
private git repository, gitignored by the outer repo (`/docs/` in the outer
`.gitignore`). Collaborators without access simply have no `docs/` folder.

- Claims point at the public sources as usual (`src/module.py`).
- Doc commit times come from the nested docs repo and source commit times
  from the outer repo, so mtime drift is still measured across the boundary.
- CI for the docs gate runs wherever both trees are present: check out the
  public repo, clone the private docs repo into `docs/`, then run
  `irminsul check`.

## Scope & Limitations

In Topology B, `irminsul context --changed` diffs the outer repo only, so
edits inside the nested docs repo do not appear in its change set — review
docs-side changes from within the docs repo instead. Publishing any part of a
private docs tree is a manual decision; nothing here automates partial
disclosure of individual docs.
