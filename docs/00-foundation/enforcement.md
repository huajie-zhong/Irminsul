---
id: enforcement
title: Mechanical Enforcement
audience: explanation
tier: 2
status: stable
describes: []
---

# Mechanical Enforcement

The point of the whole system is that you don't have to remember the rules. CI does. This technical layer provides the mechanical realization of [**The Harness Principle**](principles.md#strategic-assumptions).

## Two Tiers of Enforcement

Every check in this system falls into one of three categories:

- **Hard (deterministic, blocking).** Fail the PR. Enforce structural invariants.
- **Soft, deterministic (advisory).** Warn, badge, or open an issue. Detect drift.
- **Soft, LLM-based (advisory only).** Open an issue, never block. Catch semantic cases structural checks miss.

The boundary between hard and soft is principled: **build correctness never depends on LLM judgment.** A hallucinated finding should never prevent a merge. Hard checks are pure graph operations, set comparisons, regex, glob resolution, and git-log arithmetic — fully deterministic.

| Tier | Examples |
|------|----------|
| Hard | Frontmatter validity, glob resolution, coverage uniqueness, internal link integrity, schema-leak detection, supersession auto-update, forced reckoning on source deletion |
| Soft, deterministic | Mtime drift, external link rot, stale-doc reaper, orphan detector, ADR-touching policy reminder, Change Triplet declaration check |
| Soft, LLM | Behavioral overlap detector, semantic drift judge |

Hard checks together guarantee no PR can merge while violating the structural invariants. LLM checks exist purely to catch the residual cases — semantic duplication of purpose, prose-vs-code mismatches — and they only ever surface findings for human review.

## The Change Triplet
Every PR must touch some combination of three things: **code**, **tests**, **docs**. The PR template asks the author to declare which categories the change affects, and Danger.js (or equivalent) checks the file diff matches the declaration. Pure code changes without doc updates are flagged for justification.

## Pre-commit Hooks (run locally before push)
- Frontmatter validator (required fields present, enums valid)
- Markdown linter (style, broken syntax)
- Internal link checker (no broken `[link](other.md)`)
- Glossary linter (capitalized terms have glossary entries)
- Schema-in-component-doc detector (no SQL/Pydantic class definitions in `20-components/`)

## CI Pipeline (run on every PR)
- All pre-commit checks, plus:
- External link checker (URLs return 2xx or 3xx)
- Reference layer regeneration (T1 docs rebuilt; if the rebuild changes the output, the PR's doc preview shows the diff)
- Drift detector (for each T3 doc, compare last-commit time of `describes` files vs. the doc; warn if source is N commits or D days newer)
- Doctest runner (executable code blocks tagged `python {test}` are extracted and run)
- Orphan detector (docs with no inbound links and not in any INDEX)
- ADR-touching detector (if the PR modifies core schemas or migrations and no new ADR appears, leave a comment)
- LLM judge (advisory only — small model checks each modified component doc against its source files and opens an issue if they semantically disagree)

## Supersession Enforcement (the "Did Anyone Mark This Deprecated?" Problem)

The most insidious failure mode is silent replacement: someone writes `composer-v2.md` covering the same ground as `composer.md`, but forgets to mark the old doc deprecated. Now both exist, both look authoritative, and they slowly contradict each other. No single rule prevents this — the system uses six layered mechanisms that together make silent rot mechanically very hard:

1. **Coverage uniqueness**. Two docs cannot claim the same source paths in their `describes` fields. If `composer-v2.md` declares `describes: [app/composer/*.py]` and `composer.md` already does, CI fails. The author has three legal options: scope the new doc differently, mark the old doc deprecated (which clears its describes claim), or delete the old doc.

2. **Supersession auto-update.** When a new doc declares `supersedes: [doc-X]` in its frontmatter, CI automatically rewrites doc-X's frontmatter to set `superseded_by: <new-doc>` and `status: deprecated`. The author cannot forget — the act of declaring supersession does the marking.

3. **Forced reckoning on source deletion.** When a PR deletes source files, CI finds every doc whose `describes` field matches those files. The PR is blocked until those docs either (a) update `describes` to drop the deleted paths, (b) are themselves deleted, or (c) get `status: deprecated` with a `superseded_by` link. The author cannot merge a code deletion without explicitly resolving the doc fate.

4. **Banner injection on incoming strong links.** When a doc is marked deprecated, every doc with `depends_on: [deprecated-doc]` gets an automatic warning banner in its rendered output. Stale workflows pointing at deprecated components become visually obvious to the next reader, who will fix the reference or re-evaluate the workflow.

5. **Behavioral overlap detector (advisory).** A nightly LLM judge reads all stable docs and flags pairs that appear to describe the same component or process semantically, even when they don't share `describes` paths. Opens an issue rather than blocking — meant to catch the case where two docs cover the same conceptual ground without overlapping in the structural checks.

6. **Substantive-edit tracking.** Every doc carries a derived `last_substantive_edit` timestamp computed from git history (ignoring whitespace, frontmatter-only, and link-only changes). If a doc's substantive content hasn't changed in 12 months but its `describes` files have churned significantly, the doc is auto-flagged for review.

The combination is the point. Deleting a component forces doc resolution (3). Replacing a component forces supersession, which auto-deprecates the old (1, 2). Deprecating a component visibly poisons every dependent doc (4). And the LLM judge catches the conceptual-overlap case the structural checks miss (5). No single check is bulletproof; the layering is what makes silent contradiction nearly impossible.

## The Health Dashboard
Auto-generated daily into `90-meta/health-dashboard.md`. Tracks:

- **Coverage:** % of source files that appear in some doc's `describes` field
- **Ownership:** % of docs with a valid CODEOWNER
- **Freshness:** distribution of days-since-last-reviewed
- **Drift:** count of T3 docs where source is newer than doc
- **Orphans:** docs not referenced anywhere
- **Glossary compliance:** undefined capitalized terms by frequency
- **ADR ratio:** ADRs per 100 schema/migration changes (low ratio means decisions aren't being recorded)

These metrics make doc health visible and trackable. What gets measured gets maintained.
