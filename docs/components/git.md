---
id: git
title: Git helpers
status: stable
describes:
  - src/irminsul/git/**
owns_tests:
  - tests/test_git_blame.py
  - tests/test_git_mtime.py
  - tests/test_mtime_cross_repo.py
---

# Git helpers

The git lookups that checks and reports share live in this package, so those consumers
agree on what "last changed" and "the current change" mean. One command reads git on
its own: `check --delta` checks out the base revision in a temporary worktree.

- `mtime.py` answers when a file was last committed. `mtime-drift`, `stale-reaper`,
  `claim-provenance`, and the review queue use it. A lookup walks up from the
  file to its nearest `.git`, so a source file in a sibling repository reports that
  repository's history, and a path with no history returns an empty time instead of
  raising. History is read with one `git log` per repository and kept until
  `build_graph` starts the next graph, so code that asks for a time without building a
  graph gets the history the last graph read.
- `changes.py` lists the working tree's staged, unstaged, and untracked files for
  `context --changed` and the change lifecycle's local baseline, the changed line
  numbers `list review --changed` filters by, and a file's content at a ref, whether
  a file exists at a ref, every path tracked at a ref, the merge base of two refs, and the renames git
  detects across a range, which `diff-integrity` compares against. The whole-tree listing
  exists because asking one path at a time costs a subprocess each, and the adoption seal
  asks the same question of every path in a record that can name thousands; an unreadable
  ref answers nothing rather than an empty tree, so a failed read cannot be mistaken for
  "none of these paths was ever here".
- `blame.py` answers when each line of a file last changed, from one `git blame` per
  file, for the review queue's per-definition freshness. A line not yet committed, or a
  file git does not track, reads as changed now.

## Scope & Limitations

The helpers read history; they never write to a repository. They do not fetch, so a
shallow clone reports only the history it has. Line times come from blame over the
current file, so a deletion inside a range that leaves the remaining lines untouched is
not seen as a change.
