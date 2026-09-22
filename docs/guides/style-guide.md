---
id: style-guide
title: Style Guide
status: stable
describes: []
---

# Style Guide

Authoring conventions for docs in this repository. For the doc system's structural rules, see [`CONTRIBUTING.md`](../CONTRIBUTING.md). This guide covers authoring conventions; where a check enforces one, it says so.

## Doc IDs

The `id` field must match the filename stem, which the `frontmatter` check enforces with a certain finding. For layer index docs (`INDEX.md`), the id is the layer directory name (e.g., `components`). Never use path segments or slashes in an id — bare slugs only. <!-- irminsul:ignore prose-file-reference reason="filename convention example" -->

## What a sentence has to earn

Whoever reads a doc already has the code, symbol search, git history, and the `irminsul` queries. A sentence belongs in the doc when it saves that reader something those do not, in at least one of four ways:

- **Understanding** — a model of how parts fit that would otherwise take reading several modules, such as every check receiving only the [DocGraph](../GLOSSARY.md#docgraph), so whatever a check needs reaches it through the graph.
- **Finding** — where to start, and which component owns a responsibility.
- **Avoiding a wrong inference** — why a choice that looks odd is right, such as a baselined finding's fingerprint leaving out its line number so that a finding which only moves stays hidden.
- **Avoiding a mistake while changing code** — a gotcha, such as a check that scans a doc body having to report through `DocNode.file_line()` or landing its line numbers inside the frontmatter.

**If one file answers the sentence, it is a candidate to cut, not a verdict.** A constant's value, which function calls which, a flag's default: each copies one file and goes stale when that file changes. Weigh it against the four ways above — a why or a gotcha the file never states still earns its place — and link the file or leave it to a query only when the sentence gives none of them. Lists of commands, options, endpoints, or config keys are the strict case: they are derived on demand and never hand-copied ([Derive, don't materialize](../decisions/derive-dont-materialize.md)), and `liar` reports one.

**An explanation has one home.** A second doc links to it rather than explaining it again in other words ([Duplication-by-Paraphrase](../foundation/anti-patterns.md)). `duplicate-block` catches only a word-for-word copy, so a paraphrase is the author's to notice.

**Length follows the knowledge, not a template.** A component doc answers what the component is for, where its boundary with its neighbours lies, which constraints it keeps, and what to watch for when changing it — only the ones that have a real answer. A component with two things worth saying gets two paragraphs, plus the `## Scope & Limitations` section its layer requires.

**Describe what is; do not promote it to a rule.** "The loop records no session" reports current behaviour. "The loop must never record a session" is a constraint, and writing it needs intent a person stated — a decision record, a foundation principle, or the user's word — never an inference from the code. [Agent interface](../decisions/agent-interface.md) decided that `context` is stateless, so that sentence may be written as a rule. When no such source exists, describe the behaviour and ask.

**Removing a sentence that fails this test is a repair.** When `irminsul list review --changed` lists the deletion as `removed-sentence`, the justification is the test it failed: a copy of the named file, or a repeat of the named doc.

## Claims

A claim is a `claims:` frontmatter entry, which any layer's docs may carry; body prose names the claim it rests on with `<!-- claim:<id> -->`. The [frontmatter reference](../components/frontmatter.md) describes the fields, and [Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md) says what each `relation` means.

Most valuable prose is not a claim. A claim gives a sentence an id and cited evidence; in a pull request, removing it while that evidence survives is a finding, and so is rewording a `governs-evidence` claim without a decision record. That upkeep is worth paying only for:

- **A contract the code could break**, which a person decided to keep — `governs-evidence`.
- **A model a reader should re-check when its evidence changes** — leave `relation` out, which means `review-on-divergence`.
- **A report that is expensive to derive** — `follows-evidence`. Cheap mechanical state is an `inventory:` entry or a query, never a claim.

`claim-provenance` asks for a claim on enforcement wording such as "blocks" or "guarantees" only in the `foundation` and `architecture` layers, and as a hint.

## Prose conventions

- Write in present tense. "The check returns findings" not "The check will return findings."
- Avoid version-specific references or forward-looking language in docs outside `rfcs/` (e.g., 'ships in vN.N', 'coming soon'). Move such content to an RFC.
- One sentence per idea. Compound sentences obscure the main point.
- Limit `## Scope & Limitations` to what the component genuinely does not do. Do not list things it does not do by accident; only list things that could be confused with its purpose.

## Scope & Limitations

This guide covers authoring choices: what a sentence has to earn, when it becomes a claim, and prose style. No check decides whether a sentence earns its place; that is the author's and reviewer's judgment. Structural rules (frontmatter fields, link targets, glob patterns) are enforced by `irminsul check` and documented in [`CONTRIBUTING.md`](../CONTRIBUTING.md).
