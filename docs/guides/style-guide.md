---
id: style-guide
title: Style Guide
status: stable
summary: Authoring conventions for what a sentence earns, when it is a claim, and how an RFC's owner's part reads; a check enforces only an RFC's shape.
describes: []
---

# Style Guide

Authoring conventions for docs in this repository. For the doc system's structural rules, see [`CONTRIBUTING.md`](../CONTRIBUTING.md). This guide covers authoring conventions; where a check enforces one, it says so.

## Doc IDs

The `id` field must match the filename stem, which the `frontmatter` check enforces with a certain finding. For layer index docs (`INDEX.md`), the id is the layer directory name (e.g., `components`). Never use path segments or slashes in an id — bare slugs only.

## What a sentence has to earn

Whoever reads a doc already has the code, symbol search, git history, and the `irminsul` queries. A sentence belongs in the doc when it saves that reader something those do not, in at least one of four ways:

- **Understanding** — a model of how parts fit that would otherwise take reading several modules, such as every check receiving only the [DocGraph](../GLOSSARY.md#docgraph), so whatever a check needs reaches it through the graph.
- **Finding** — where to start, and which component owns a responsibility.
- **Avoiding a wrong inference** — why a choice that looks odd is right, such as a baselined finding's fingerprint leaving out its line number so that a finding which only moves stays hidden.
- **Avoiding a mistake while changing code** — a gotcha, such as a check that scans a doc body having to report through `DocNode.file_line()` or landing its line numbers inside the frontmatter.

**If one file answers the sentence, it is a candidate to cut, not a verdict.** A constant's value, which function calls which, a flag's default: each copies one file and goes stale when that file changes. Weigh it against the four ways above — a why or a gotcha the file never states still earns its place — and link the file or leave it to a query only when the sentence gives none of them. Lists of commands, options, endpoints, or config keys are the strict case: they are derived on demand and never hand-copied ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)). Name the ones a sentence means in code spans, where `code-references` reports one that is gone, and keep a curated list as an `inventory:` entry, which checks it against the code.

**An explanation has one home.** A second doc links to it rather than explaining it again in other words ([Duplication-by-Paraphrase](../foundation/anti-patterns.md)). `duplicate-block` catches only a word-for-word copy, so a paraphrase is the author's to notice.

**Length follows the knowledge, not a template.** A component doc answers what the component is for, where its boundary with its neighbours lies, which constraints it keeps, and what to watch for when changing it — only the ones that have a real answer. A component with two things worth saying gets two paragraphs, plus the `## Scope & Limitations` section its layer requires.

**Describe what is; do not promote it to a rule.** "The loop records no session" reports current behaviour. "The loop must never record a session" is a constraint, and writing it needs intent a person stated — a decision record, a foundation principle, or the user's word — never an inference from the code. [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) decided that `context` is stateless, so that sentence may be written as a rule. When no such source exists, describe the behaviour and ask.

**Removing a sentence that fails this test is a repair.** When `irminsul list review --changed` lists the deletion as `removed-sentence`, the justification is the test it failed: a copy of the named file, or a repeat of the named doc.

## Claims

A claim is a `claims:` frontmatter entry, which any layer's docs may carry; body prose names the claim it rests on with `<!-- claim:<id> -->`. The [frontmatter reference](../components/frontmatter.md) describes the fields, and [Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md) says what each `relation` means.

Most valuable prose is not a claim. A claim gives a sentence an id and cited evidence; in a pull request, removing it while that evidence survives is a finding, and so is rewording a `governs-evidence` claim without a trailer naming it. That upkeep is worth paying only for:

- **A contract the code could break**, which a person decided to keep — `governs-evidence`.
- **A model a reader should re-check when its evidence changes** — leave `relation` out, which means `review-on-divergence`.
- **A report that is expensive to derive** — `follows-evidence`. Cheap mechanical state is an `inventory:` entry or a query, never a claim.

No check asks for a claim because of how a sentence is worded ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)). Whether a sentence must stay true is the author's call, and declaring the claim is how the author makes it.

## The owner's part of an RFC

An RFC has two readers, and the owner is the one who decides ([RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)). Everything above `## Design detail` is the owner's part: written for a person, in plain words, and short enough to decide from in the time the change deserves. `irminsul new rfc` writes the layout and `rfc-structure` keeps its shape.

- **The weight sets how much the owner reads.** A `small` RFC is a sign-off, such as changing an exit code to match a rule: a Summary that says what changes and what the owner signs off on, and Decisions, read in 5 to 30 seconds. A `large` RFC changes a decision or the foundation, breaks adopters, adds or removes a check or a command, or migrates data or history; it gets all five sections and reads in about two minutes. The author proposes the weight and the owner may change it. Nothing counts words or guesses a weight, so the two minutes are a guideline for the author.
- **Summary** gives the gain first, then how, then how many decisions need the owner, so a reader with no questions can stop there.
- **Problem** is one worked example with named items and numbers, not a general description, told in plain words; the exact commands and names it rests on go under `## Design detail`.
- **How it works** is the mechanism at a level the owner can question: what is general, where it can grow, and what it leaves out.
- **Cost and risk** says what the change costs and what could go wrong.
- **Decisions** lists each choice with its options, the two or three factors that decide it and a recommendation, and later the owner's answer.
- **Define a term where it first appears,** and put a name in a code span only where the exact name matters. A paragraph of four or more code spans is probably a list of names that belongs under `## Design detail`, which is why `rfc-structure` hints at it; one that needs its names keeps an ignore comment that says why.
- **The agent's part starts at `## Design detail`.** Every list of names, files, ids and migration steps goes there, then `## Requirements` and `## Tasks`. No check can tell whether a decision was buried in it, so review has to.

## Prose conventions

- Write in present tense. "The check returns findings" not "The check will return findings."
- Avoid version-specific references or forward-looking language in docs outside `rfcs/` (e.g., 'ships in vN.N', 'coming soon'). Move such content to an RFC.
- One sentence per idea. Compound sentences obscure the main point.
- Limit `## Scope & Limitations` to what the component genuinely does not do. Do not list things it does not do by accident; only list things that could be confused with its purpose.

## Scope & Limitations

This guide covers authoring choices: what a sentence has to earn, when it becomes a claim, how to write an RFC's owner's part, and prose style. No check decides whether a sentence earns its place or whether an owner's part is plain enough; that is the author's and reviewer's judgment, and `rfc-structure` reads only the shape. Structural rules (frontmatter fields, link targets, glob patterns) are enforced by `irminsul check` and documented in [`CONTRIBUTING.md`](../CONTRIBUTING.md).
