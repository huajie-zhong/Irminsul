---
id: a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts
title: "A sentence about behaviour is anchored to the test that asserts it"
status: draft
summary: "The loop, the scaffolds and the agent protocol advise anchoring a sentence that says what code does to the test that asserts it, `anchors --suggest` offers those tests, and whoever adds such an anchor sees the test fail once."
describes: []
rfc_state: draft
affects:
  - anchors
  - init
  - new-list-regen
weight: large
---

# A sentence about behaviour is anchored to the test that asserts it

## Summary

A sentence that says what code does can be tied to the test that checks it. It is then asked
about again exactly when that check changes, and the check fails when the code stops doing
what the sentence says. The tie already works; nothing Irminsul ships tells an agent to make
it. This adds the advice to the loop, the scaffolds and the agent protocol, has the command
that suggests anchors offer tests, and asks whoever adds such a tie to see the test fail
once. Three decisions, all answered.

## Problem

A guide says "the fine stops growing at 5 dollars". The code is one function, and one test
asserts the cap.

Leave the sentence untied, and nothing asks about it when the cap becomes 8 dollars: the
guide owns no code. Tie it to the function, and it is asked about on every edit to that
function, a reworded docstring included, and not at all when the cap moves into a function
it calls.

Tie it to the test, and neither happens. A change that moves the cap fails the test, so the
change cannot merge until the test is edited, and editing the test asks about the sentence.

In the seeded-rot suite 3 of 11 false sentences are pointed at, each through an anchor or a
claim. In this repository 11 of 91 anchors name a test: ten written by the command that
finalizes an [RFC](../GLOSSARY.md#rfc), and one by hand. The loop names tests once, to say they are run before a
commit.

## How it works

**An anchor may name a test.** This exists: an anchor names a file and a definition in it, a
test function is one, and its paragraph is asked about when that function changes.

**What Irminsul ships says so.** The loop's step on writing docs, the comment a new component
doc starts with, and the agent protocol gain the advice: a sentence about what code does is
best tied to the test that asserts it.

**The suggesting command offers tests.** For a name a doc uses, it lists where the name is
defined; it will also list the tests that use it, each as a marker ready to paste.

**See it fail once.** Whoever ties a sentence to a test changes the code so the sentence is
false, runs the test and sees it fail, then restores the code. A test that still passes does
not guard the sentence. This is a written step: Irminsul runs no code.

**What it leaves out.** It does not measure how much of a function its tests guard, and it
says nothing about a sentence that gives a reason and no behaviour.

## Cost and risk

Wording in three shipped texts, and a reading of the test files by the suggesting command.

The risk is a tie that looks like protection and is none: a sentence tied to a test that does
not check it. Seeing the test fail is the only guard, and nothing verifies that it was done.
A test edited for another reason also asks about its paragraphs again, which is a reading and
not an error.

## Decisions

Answered by the owner on 2026-11-26:

1. **The advice ships to every adopter**, in the loop's template, the component scaffold and
   the agent protocol, and not in this repository's own guidance alone.
2. **Seeing the test fail is a written step.** A command that breaks the code in many ways
   and reports which of them the tests miss is left to the backlog.
3. **The suggesting command offers tests** beside the definitions it offers today.

## Design detail

- **Today.** Step 3 of the loop (`src/irminsul/init/scaffolds/AGENTS.md.j2`, and the root
  `AGENTS.md` a test keeps equal to it) says to "name that code in a code span, anchor the
  paragraph to it, or declare it as a claim with evidence". The comment in
  `src/irminsul/new/templates/component.md.j2` lists the same three ways. The agent protocol
  and the skill say nothing of tests. `docs/components/anchors.md` says a marker names "a file
  and (optionally) a symbol", which a test satisfies, and `change finalize` wrote ten of the
  eleven anchors that name a test.
- **The loop.** Step 3 gains one sentence: a sentence that says what the code does is best
  anchored to the test that asserts it, since it is then asked about when that test changes
  and the test fails when the code stops doing it.
- **The component scaffold.** Its comment gains the same advice as a fourth line.
- **The agent protocol.** `docs/guides/agent-protocol.md` and its scaffold gain a short
  procedure for tying a sentence to a test. Find the test, with `irminsul anchors --suggest`.
  Change the code so the sentence is false, run the test and see it fail, and restore the
  code. Paste the marker and pin it, as an anchor to code is pinned. A test that does not
  fail is the wrong test, or the sentence has none yet.
- **The suggesting command.** `suggest` in `src/irminsul/binding.py` offers up to three
  definitions of a name from the source roots. For each Python definition it will also offer
  up to three test functions, from the files under `paths.test_roots` that import the
  defining module, whose body names that definition, each printed as a marker like the
  definitions. JSON carries them under the candidate. A test file that does not parse is
  skipped, as a source file is. Another language's tests are not offered: a suggestion names
  only what an anchor can resolve.
- **What already works.** An anchor to a test resolves, is pinned and drifts like any other:
  `claim-anchor/pinned-drift`, a hint a re-pin answers after the paragraph is re-read.
- **The seeded-rot suite** gains a case whose sentence is anchored to a test of its fixture:
  the edit that makes the sentence false makes that test fail, and editing the test to pass
  again draws `pinned-drift` on the sentence's paragraph.
- **Governing records.** `code-is-named-in-code-spans-and-bound-by-anchors` decides anchors
  and what the suggesting command prints;
  `agents-get-stateless-read-only-queries-and-one-written-loop` decides the loop and the
  protocol. Each states its part in place with a dated Changes item.
- **Backlog.** A command that changes a function in several small ways, runs the tests its
  paragraphs are anchored to, and lists the changes no test noticed. It runs code, so it is
  no check, and each language runs tests its own way.
- **Not chosen.** A check that asks every sentence about behaviour for a test: no check knows
  which sentences state behaviour. Formal verification of a function against its sentences:
  writing the specification is the cost, and a test is the specification this project has.

## Requirements

### Requirement: The suggesting command offers the tests of a definition
ID: suggest-offers-the-tests-of-a-definition
Provenance: code

`irminsul anchors --suggest` SHALL list, with each Python definition it offers for a name, up
to three test functions in files under the configured test roots that import the defining
module and whose body names that definition, each as an anchor marker ready to paste.

#### Scenario: A test calls the function
- **WHEN** a doc names `` `late_fee()` `` with no anchor, `src/loans/policy.py` defines it, and `test_fee_is_capped` in `tests/test_loans.py` imports that module and calls it
- **THEN** `anchors --suggest` offers the definition and, with it, a marker for `tests/test_loans.py#test_fee_is_capped`

#### Scenario: No test names it
- **WHEN** no test function names the definition
- **THEN** `anchors --suggest` offers the definition alone

## Tasks

- `T1` Offer the tests of a definition in `suggest`, in the plain output and the JSON. (req: suggest-offers-the-tests-of-a-definition)
- `T2` Add the advice to step 3 of the root `AGENTS.md` and its template, and to the comment of the component scaffold. (component: init)
- `T3` Add the procedure for tying a sentence to a test to the agent protocol and its scaffold. (component: init)
- `T4` Add the seeded-rot case of a sentence anchored to a test. (component: anchors)
- `T5` State the rules in the two governing records with dated Changes items, and record the command left out in the backlog. (component: anchors)
