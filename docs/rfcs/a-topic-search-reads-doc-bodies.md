---
id: a-topic-search-reads-doc-bodies
title: "A topic search reads doc bodies"
status: stable
describes: []
rfc_state: accepted
affects:
  - context
resolved_by: docs/decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md
summary: "`context --topic` matches words in doc bodies too, ranked below matches in a doc's title, summary or headings, so a topic named only in prose, such as a non-goal, is found."
required_updates: []
weight: small
---

# A topic search reads doc bodies

## Summary

A topic search also finds a doc whose body uses the words, ranked after the docs whose title,
summary or headings do. Today it reads only those fields, so in the 2026-10-29 dogfood a search
for "budget" found nothing although the foundation lists budgets as a non-goal, and the agent
built the feature anyway. One decision, answered.

## Decisions

Answered by the owner on 2026-10-29:

1. **Search bodies too, ranked below the other fields**, rather than leaving bodies to grep.

## Design detail

- **Today.** `context --topic <query>` matches every word of the query against a doc's id,
  title, path, `describes`, tests, tags, `summary` and headings, and says "the words may appear
  only in doc bodies, so search them directly" when nothing matches.
- **The rule.** A doc matches when every word appears in those fields or in its body prose; a
  doc that matches only through its body ranks below every doc that matches without it. Words
  are matched as today (case-folded tokens), not as meaning. The packet's cap applies, with the
  count of the rest. The body is the graph's parsed text, so no file is read twice.
- **The hint.** "search them directly" goes once bodies are searched.
- **Evidence.** Agents B and D of the dogfood each got `(none)` for a topic whose words were in
  doc bodies (`list --json`, `budget`).
- **Governing record.** `agents-get-stateless-read-only-queries-and-one-written-loop`.

## Requirements

### Requirement: A topic search matches body prose
ID: topic-search-matches-body-prose
Provenance: code

`context --topic` SHALL return a doc whose body prose contains every word of the query, ranked
below each doc that matches through its id, title, path, `describes`, tests, tags, `summary` or
headings.

#### Scenario: A non-goal in the foundation
- **WHEN** the foundation's principles doc says "budgets" only in its body and `context --topic budget` runs
- **THEN** the result includes that doc

#### Scenario: A heading match ranks first
- **WHEN** one doc has "budget" in a heading and another only in its body
- **THEN** the heading match is listed first

## Tasks

- `T1` Match body prose and rank body-only matches last. (req: topic-search-matches-body-prose)
- `T2` Drop the "search them directly" hint. (component: context)

## Resolution

Accepted by the owner on 2026-10-29, with the answer recorded under Decisions, and resolved by [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md), whose Changes item records it. Each rule joins its record's Decision with the implementation, as an edit in place once decision records are living topics.
