---
id: records-are-named-by-slug
title: Records are named by slug
status: stable
describes: []
summary: RFCs and decision records are files named by a slug of their title, with no number; order and relationships come from links and git, not from the filename.
---

# Records are named by slug

## Status

Accepted, 2026-09-15.

## Context

RFCs and decision records were numbered: `irminsul new` took one past the highest number on
disk or anywhere in the folder's git history. Branches that had not fetched each other
both picked the same number, and because the filenames differed git reported no conflict,
so both merged. Numbers also invited prose such as "ADR-0029" that names a record without
linking it, and nothing mechanical checks such a name.

What a number offered was order. Nothing in the tool needs it: replacement is explicit in
`supersedes`, `change graph` derives relationships from links, the lifecycle queue groups
by state, and git history records when each file landed.

## Decision

- **A record is named by the slug of its title.** `irminsul new adr "Cache sharding"`
  writes the file named by the slug `cache-sharding` in the decisions layer, with the slug as its `id` and the
  title as written; `irminsul new rfc` does the same in the RFC layer. A slug is the
  title lowercased, with words joined by hyphens.
- **A name is taken once.** `irminsul new` refuses a slug whose file exists. Two branches
  that pick the same slug collide on the same path, which git reports as a conflict about
  one topic.
- **Records are referenced by link.** Prose names a record through a Markdown link to its
  file, which `links` checks; a decision wording that links no decision record is a
  `reality/unrecorded-decision` hint.
- **No stored order.** Records carry no creation date; where order matters, commands
  derive it from links or state, and `git log` shows when a record landed.
- **Existing records are renamed** to their slugs, with titles and links updated, in one
  deliberate change. That change was expected to wait for the release history reset,
  because renaming a record read as deleting it; once `diff-integrity` learned to follow
  git's renames it became an ordinary reviewable commit, and the numbered records were
  renamed on the main branch.

## Alternatives Considered

- **Keep numbers and report two records sharing one.** Rejected: it fixes the collision
  after both branches merged and keeps a number that nothing needs.
- **Prefix a creation date.** Rejected: the date a branch started a record is not the date
  it landed, and a reset that squashes history loses it anyway.
- **Stamp a `created` field.** Rejected: no command needs the order, so the field would be
  maintained for nothing.

## Consequences

- Long titles make long filenames, which is the cost of self-describing names.
- Scripts or links that named a record by number break once, at the rename.
