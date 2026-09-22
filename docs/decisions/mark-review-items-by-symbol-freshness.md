---
id: mark-review-items-by-symbol-freshness
title: Mark review items by symbol freshness
status: stable
describes: []
summary: The review queue marks a sentence only when the definition it names changed after the doc, and shows marked sentences by default.
---

# Mark review items by symbol freshness

## Status

Accepted, 2026-09-13.

## Context

The review queue listed every checkable sentence and marked those whose referenced
file changed after the doc. Busy files marked almost everything, so the queue handed
agents mostly true sentences.

## Decision

Mark a review item only when a line of a referenced definition — a function's or class's
full range, a surface identity's declaring line, or a whole file for a path — was last
changed after the doc's last commit, using one `git blame` per referenced file.
Uncommitted lines count as changed. Show only marked items by default; `--all` shows the
full queue, and the JSON reports both counts.

## Alternatives Considered

- **File-level marking.** Rejected: it marks nearly every sentence about a busy file.
- **A stored reviewed stamp per sentence.** Rejected: the queue is derived on every call.
- **`git log -L` per reference.** Rejected: one process per reference, where blame
  answers a whole file at once.

## Consequences

- The default queue is short enough to hand to an agent.
- Behaviour changed through code a sentence does not name goes unmarked; `--all` covers
  that case.
