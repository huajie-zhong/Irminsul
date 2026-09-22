---
id: splitting-a-doc-keeps-one-description
title: "Splitting a doc keeps one description of the code"
status: stable
describes: []
summary: A new component doc cannot take files another doc owns without naming that doc; moved files and unlinked overlapping claims surface as hints and review items.
---

# Splitting a doc keeps one description of the code

## Status

Accepted, 2026-09-15.

## Context

`uniqueness` reports two docs that claim a file at the same specificity. It cannot see
the quieter duplication: an agent writes a new doc with a narrower claim on files an
existing doc already covers. The narrower claim wins, so each file still has one owner
and nothing fails, while the old doc keeps its paragraphs about those files. Two
descriptions of the same code then drift apart, and a reader of either never learns the
other exists.

## Decision

- **`irminsul new component` refuses** a `--describes` value that matches a file another
  doc owns today, unless each owner is named with `--split-from <doc-id>`. The new doc
  then opens with a `Split from` link to each owner, and the command prints which files
  to remove from the owner's claim and prose.
- **A moved owner is a hint under `--diff`** (`diff-integrity/owner-changed`): a source
  file owned by one doc at the merge base and by another now.
- **`irminsul list review --changed` lists the old owner's sentences** that name a moved
  file by path or file name, with a `moved-file` marker, so the writer rereads them.
- **An unlinked overlap is a hint** (`uniqueness/unlinked-overlap`): a doc whose claim
  wins files a broader claim in another doc also matches, when neither doc links the
  other.

## Alternatives Considered

- **Make a moved owner certain.** Rejected: moving files between docs is a normal
  refactor, and the tool cannot tell whether the old prose was cleaned up.
- **Compare the prose of the two docs for similarity.** Rejected: judging whether two
  paragraphs say the same thing is semantic work for the agent, not a mechanical rule.

## Consequences

- An agent that means to split a doc says so on the command line, and the link it writes
  lets `unlinked-overlap` stay quiet.
- An overlap created by editing frontmatter by hand, not through `new`, is caught only by
  the two hints.
