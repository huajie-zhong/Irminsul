---
id: git
title: Git helpers
status: stable
summary: Git helpers for changed paths, commit times, and blame.
depends_on:
  - user-errors
describes:
  - src/irminsul/git/**
owns_tests:
  - tests/test_git_blame.py
  - tests/test_git_changed_since.py
  - tests/test_git_mtime.py
  - tests/test_git_reader.py
  - tests/test_mtime_cross_repo.py
---

# Git helpers

The git lookups that checks and reports share live in this package, so those consumers
agree on what "last changed" and "the current change" mean. One command reads git on
its own: `check --delta` checks out the base revision in a temporary worktree.

`mtime.py` answers when a file last changed, for the checks that compare commit times,
such as `mtime-drift` and `claim-provenance`. A lookup walks up from the file's resolved
path to its nearest `.git`, so a source file in a sibling repository reports that
repository's history, and a path with no history returns an empty time instead of raising.
A path that `git status` lists, whether staged, unstaged, or untracked and not ignored,
reads as one pending instant instead of its last commit: the end of the run's day, later
than every commit made by then and equal to itself, so an uncommitted edit counts as the
commit it will become and a doc and the file it cites that were both edited are changed
together, neither after the other. A graph built with `committed_only` has no pending
instant, and every reader of history returns to commits alone.
<!-- anchor: src/irminsul/docgraph.py#DocGraph.committed_only @sha256:f2bca604de9b -->

`changes.py` holds `changed_since`, the one answer to what changed since a base ref
([A change is judged from its merge base to the working tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md)).
`check --diff`, `--source-diff`, `context --after-edit`, `change status` and `verify` all
ask it, so the commands that judge a change agree. The rest of the module answers questions
at a ref (a file's content, whether it exists, every tracked path, a merge base, renames,
trailers) and lists the working tree's staged, unstaged and untracked files. For a command
run with no base it can also say how many commits `HEAD` holds that the default branch's
remote ref lacks, `unmerged_branch_commits`, so that command can name the base it did not use.

`reader.py` holds `GitReader`, which every helper here asks through. It runs a git command
at most once per reader and keeps only the answers a run cannot change (what a commit, a
ref or the history holds), while what the working tree holds is asked every time, because
writing a file changes it. A graph owns one, `graph.git`, so a run's checks share answers
and the next graph asks again; a command with no graph makes its own.

`blame.py` answers when each line of a file last changed, for the review queue's
per-definition freshness; an uncommitted line reads as changed at the reader's pending
instant.

## Scope & Limitations

The helpers read history; they never write to a repository. They do not fetch, so a
shallow clone reports only the history it has. Line times come from blame over the
current file, so a deletion inside a range that leaves the remaining lines untouched is
not seen as a change.
