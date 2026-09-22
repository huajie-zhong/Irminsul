---
id: drafts-excuse-an-unfinished-doc-not-a-wrong-one
title: "Drafts excuse an unfinished doc, not a wrong one"
status: stable
describes: []
summary: A certain finding is demoted on a draft doc only when its code reports the doc as unfinished; a finding about the doc's relationship to code or to other docs is an error whatever the doc's status.
---

# Drafts excuse an unfinished doc, not a wrong one

## Status

Accepted, 2026-09-15. Refines
[Finding classes decide what blocks](finding-classes-decide-what-blocks.md).

## Context

[Finding classes decide what blocks](finding-classes-decide-what-blocks.md) made
every certain finding an error, except on a doc whose `status` is `draft`, where it
stayed a warning because the doc is work in progress. The rule read the doc's status and
nothing else, so it applied to every certain code alike.

That made `status: draft` the cheapest green run in the system. An agent facing a broken
link, a missing anchored symbol, or a rewritten implemented record could change one word
of frontmatter and watch the error become a warning — and the workflow `irminsul init`
scaffolds does not pass `--strict`, so the run went green. The status is read from the
document in the change under review, so the demotion could be applied in the same commit
that broke the record it was hiding. Nothing reported a stable document becoming a draft,
and nothing reported how long one had been a draft.

The demotion was worth keeping for what it was written for. A doc being drafted really is
missing its `## Scope & Limitations` section, and an RFC being drafted really does not
have its requirements finished; failing the build for that would make writing a document
impossible until it was finished.

## Decision

- **A certain code declares whether a draft excuses it.** A check may declare
  `drafts_exempt`, the subset of its certain codes that report a doc as unfinished rather
  than as wrong about something outside it. Only those are demoted to warnings on a draft.
- **Everything else is an error whatever the status.** A broken link, a missing anchored
  symbol, an unknown id in `supersedes`, a rewritten implemented record: a half-written
  document may be half-written, but it may not point at something that does not exist.
- **The exempt set is declared, not enumerated centrally.** It sits beside `classes` in
  the check that owns the code, so a new code is classified where it is written and no
  hand-kept list elsewhere can fall behind.

## Alternatives Considered

- **Demote only on a doc that did not exist at the merge base.** Rejected: it needs a diff
  and a git history to answer, so it falls back to the old behaviour on a plain
  `irminsul check`, leaving the default branch uncovered — and the checks that read git
  history are exactly the ones a shallow checkout silences.
- **Report the `stable` to `draft` transition and keep the blanket demotion.** Rejected as
  insufficient on its own: it catches the flip in review but leaves a document born as a
  draft hiding its errors indefinitely. It remains worth adding separately.
- **Drop the demotion entirely.** Rejected: a freshly scaffolded doc would fail the gate
  until it was finished, which punishes the act of starting to write.

## Consequences

- A repository with draft docs carrying broken links or missing anchors sees new errors on
  the first run after upgrading. They were always errors; the status was hiding them.
- Classifying a new certain code now has a second question — is it about this doc being
  unfinished? — answered in the same place as its class.
- `status` remains a statement about the document, not a control on the gate, so the two
  cannot be confused.
