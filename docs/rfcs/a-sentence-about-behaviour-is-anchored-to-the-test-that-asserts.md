---
id: a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts
title: "A sentence about behaviour is anchored to the test that asserts it"
status: stable
describes: []
rfc_state: implemented
affects:
  - anchors
  - init
  - new-list-regen
  - cli
  - context
resolved_by: docs/decisions/code-is-named-in-code-spans-and-bound-by-anchors.md
summary: "The loop, the scaffolds and the agent protocol advise anchoring a sentence that says what code does to the test that asserts it, `anchors --suggest` offers those tests, and whoever adds such an anchor sees the test fail once."
required_updates: []
weight: large
---

# A sentence about behaviour is anchored to the test that asserts it

## Summary

A sentence that says what code does can be tied to the test that checks it. It is then asked
about again exactly when that check changes, and the check fails when the code stops doing
what the sentence says. The tie already works; nothing Irminsul ships tells an agent to make
it. This adds the advice to the loop, the scaffolds and the agent protocol, has the command
that suggests anchors offer tests, and asks whoever adds such a tie to see the test fail
once. Five decisions, all answered: two were added on 2026-11-26 after a review of the build.

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
claim. In this repository 11 of 90 anchors name a test: ten written by the command that
finalizes an [RFC](../GLOSSARY.md#rfc), and one by hand. The loop names tests once, to say they are run before a
commit.

## How it works

**An anchor may name a test.** This exists: an anchor names a file and a definition in it, a
test function is one, and its paragraph is asked about when that function changes.

**What Irminsul ships says so.** The loop's step on writing docs, the comment a new component
doc starts with, and the agent protocol gain the advice: a sentence about what code does is
best tied to the test that asserts it.

**The suggesting command offers tests.** Today it lists only the names in a doc that resolve
to no code, with where each could be defined. Asked about one doc, it will also list each
function or class that doc names, with the tests that name it, each as a marker ready to
paste. A test names a function when it reaches it through its file's imports; a local of
the same spelling does not count. For a sentence that names no code, the packet for a source
file a doc owns lists the tests that import it. Both read only the test directories the
configuration declares; where it declares none, the reader is told to search the tests for
the name.

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
3. **The suggesting command offers tests for the functions and classes a doc names**, when it
   is asked about one doc. First written as "beside the definitions it offers today": a review
   found that it offers a definition only for a name that resolves to nothing, so that
   wording would have offered a test for almost no sentence.

Added by the owner on 2026-11-26, after a review of the build:

4. **A test names a definition through its file's imports.** A review found that matching the
   name anywhere in a test's body offered, on five docs of this repository, 23 of 70 tests
   that never touch the function: a parameter, a local or a fixture spelled the same. A method
   is still matched by its name, since the syntax tree does not say what class an object has.
5. **Where the configuration declares no test root, the procedure says so** and sends its
   reader to search the tests for the function's name. `irminsul init` declares none, because
   a declared test root asks for an owner for every test file in it; reading tests without
   that promise is left to a later RFC, with what a new repository's gate fails on.

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
  procedure for tying a sentence to a test. Find the test: once the configuration declares
  its test roots, `irminsul anchors --suggest --doc <doc>` lists the tests that name a
  function the doc names, and `irminsul context <source file>` the tests that import a file a
  doc owns, for a sentence that names no code; otherwise, or when neither lists one, search
  the tests for the function's name (decision 5).
  Change the code so the sentence is false, run the test and see it fail, and restore the
  code. Paste the marker and pin it, as an anchor to code is pinned. A test that does not
  fail is the wrong test, or the sentence has none yet.
- **The suggesting command.** `irminsul anchors --suggest` lists each unbound name, a code
  span that resolves to nothing, with up to three places that define it, from the source
  roots (`suggest` in `src/irminsul/binding.py`, printed by `_suggest_anchors` in
  `src/irminsul/cli.py`). A function with one definition resolves, so it is not listed.
  Given `--doc <doc>`, the command will also list each code span of that doc that resolves to
  one Python function or class, with up to three test functions that name it. A test
  function is a function whose name starts with `test`, in a Python file under
  `paths.test_roots` that imports the defining module, which is the reading `Ranker` in
  `src/irminsul/ranked_tests.py` already makes for the packet. It names a top-level function
  or class when its body uses a name the file imported from the defining module, under an
  alias too, that the test does not bind itself, or an attribute of a name the file bound to
  that module; it names a method when its body reads an attribute of the method's name and
  its file imports the class or its module (decision 4). With no test root declared, the
  listing says that no test file was read. They are ordered by path and
  line and printed as markers like the definitions. A name no test names is listed too, and
  said to have none. The JSON keeps `unbound` and its version, and under `--doc` gains a list
  `resolved`: each row holds the doc's path and line, the name, where it is defined, and its
  `tests`. The closing line counts these names apart from the unbound ones. A test file that
  does not parse is skipped, as a source file is. Without `--doc` the output is as today.
  Tests in another language are not offered yet.
- **A sentence that names no code.** The procedure sends its reader to
  `irminsul context <source file>`, whose packet lists the tests that import that file when
  the configuration declares test roots and a doc owns the file.
- **The skill** is unchanged: it points at the root `AGENTS.md`, which holds the loop.
- **What already works.** An anchor to a test resolves, is pinned and drifts like any other:
  `claim-anchor/pinned-drift`, a hint a re-pin answers after the paragraph is re-read.
- **The seeded-rot suite** gains a case whose sentence is anchored to a test of its fixture.
  The fixture's test file, a placeholder today, gains that test. It imports a package only
  the fixture has, so this repository's own test run is kept from collecting it, as
  collection would fail at the import. The case shows two things: the edit that makes the
  sentence false makes the test fail, run as the suite's probes run the fixture's code; and
  editing the test to pass again draws `pinned-drift` on the sentence's paragraph.
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

`irminsul anchors --suggest --doc <doc>` SHALL list each code span of that doc that resolves
to one Python function or class, with up to three test functions, in files under the
configured test roots that import the defining module, whose body names that definition
through the file's imports, each as an anchor marker ready to paste. A name the test binds
itself SHALL NOT count as naming the definition. Without `--doc` it SHALL list what it lists
today.

#### Scenario: A test calls the function
- **WHEN** `irminsul anchors --suggest --doc docs/guides/lending.md` runs, the guide names `` `late_fee()` ``, `src/loans/policy.py` defines it, and `test_fee_is_capped` in `tests/test_loans.py` imports that module and calls it
- **THEN** the output lists `late_fee` with a marker for `tests/test_loans.py#test_fee_is_capped`

#### Scenario: A local of the same spelling
- **WHEN** a test file imports `loans.policy` and a test's parameter is called `late_fee`, which its body uses, and the guide names `` `late_fee()` ``
- **THEN** the output does not offer that test for `late_fee`

#### Scenario: No test names it
- **WHEN** no test function names the definition
- **THEN** the output lists that name and says no test names it

#### Scenario: No doc is given
- **WHEN** `irminsul anchors --suggest` runs with no `--doc`
- **THEN** it lists the unbound names and their definitions, and no test

## Tasks

- `T1` Offer the tests of each function or class a doc names under `anchors --suggest --doc`, in the plain output and the JSON. (req: suggest-offers-the-tests-of-a-definition)
- `T2` Add the advice to step 3 of the root `AGENTS.md` and its template, and to the comment of the component scaffold. (component: init)
- `T3` Add the procedure for tying a sentence to a test to the agent protocol and its scaffold. (component: init)
- `T4` Add the seeded-rot case of a sentence anchored to a test. (component: anchors)
- `T5` State the rules in the two governing records with dated Changes items, and record the command left out in the backlog. (component: anchors)

## Resolution

Accepted by the owner on 2026-11-26, with the answers recorded under Decisions, decisions 4
and 5 added the same day, and resolved by [Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md), whose Changes item records it. [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) records its part too. Each rule joins its record's Decision with the implementation, as an edit in place.
