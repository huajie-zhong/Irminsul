---
id: each-language-reads-its-code-through-one-interface
title: "Each language reads its code through one interface"
status: stable
describes: []
rfc_state: accepted
affects:
  - languages
  - anchors
  - new-list-regen
  - context
  - checks
  - surface
resolved_by: docs/decisions/surface-rules-and-language-profiles-are-data.md
summary: "Every feature that asks what a file defines, on which lines, what it imports or what a function body refers to asks one interface, which Python answers through its own parser and TypeScript, Go and Rust through tree-sitter, so a feature reaches every language and a language is added in one place."
required_updates: []
weight: large
---

# Each language reads its code through one interface

## Summary

A feature that needs to know what a file defines, where a definition starts and ends, what a
file imports, which names a function body refers to, or which functions are tests asks
Python's own parser today, in five modules. So each feature built that way reaches Python alone: binding a code span to a
function, the review queue that re-asks a sentence when its function changes, the tests a
packet lists, the tests `anchors --suggest` offers, and `import-deps`. This proposes one
interface that asks those five questions of any language. Python answers through its parser
as today; TypeScript, Go and Rust answer through tree-sitter, the route
`claim-evidence-names-a-part` already records. A feature asks the interface and reaches
every language that answers, and adding a language is a profile, a grammar package and a
file of queries. The owner put it on the roadmap on 2026-11-26 and answered its six decisions
on 2026-11-27.

## Problem

A TypeScript project adopts Irminsul. Its guide says "`lateFee()` caps the fine at 5
dollars", and that function lives in one file of the project. A change edits its body. In a
Python project the same change queues the guide's sentence for a re-read; here the queue
holds nothing, the packet for the file lists no test that imports it, and the command that
suggests anchors offers none. The adopter is told nothing is wrong.

Each feature added on 2026-11-26 was built on Python and had to say so: the [RFC](../GLOSSARY.md#rfc) that re-asks
sentences naming changed code pairs Python's functions alone (its decision 6), and the RFC on
anchoring to tests offers Python's tests alone. The next feature will do the same unless
there is something else to ask.

A person adding a language today writes a profile, as
[`surface-rules-and-language-profiles-are-data`](../decisions/surface-rules-and-language-profiles-are-data.md)
promises, and gets none of the features above. The pattern that finds its environment
variables also lives outside the profile, in `src/irminsul/inventory/env_vars.py`.

## How it works

**One interface, five questions.** For a file, a language answers: the definitions in it
(each function, class or type and each method, with its name, the type that holds it, and its
first and last line, decorators and attributes included); the repository files it imports and
the names each import binds; the names a definition's body refers to; a definition's canonical
text, which a pin hashes so that a comment or a reformat does not move it; and which of its
definitions are tests, by the language's own convention.

**Python keeps its parser.** Its answers come from `ast` as today, so no Python pin of any
adopter moves.

**TypeScript, Go and Rust answer through tree-sitter**, a parser library with one grammar
package per language and one query language for all. Each language has a file of queries
that says what a definition and an import look like in its grammar. A probe on 2026-11-26
read a TypeScript function, class, method and arrow function, a Go type, function and method,
and a Rust struct, impl block and function, each with its first and last line, and each
file's imports, from about five lines of query per language.

**Features ask the interface.** The five modules that call Python's parser for these
questions call the interface instead, once, and nothing in a check names a language. So the
queue, the packet's tests, the suggested tests and `import-deps` reach TypeScript, Go and Rust
when this lands, `import-deps` as far as decision 9 lets it.

**Adding a language** is a profile, a grammar package and a query file, with a fixture that
tests the queries. The environment variable pattern moves into the profile, so a language's
facts are in one place.

**What it leaves out.** Framework surfaces stay as the record decides: syntax-tree
extractors for Typer, FastAPI and an MCP server, rules for the rest. An import is resolved to
a repository file where the language says so plainly (a relative path, a module under a
source root, a Go package under the module path, a Rust `crate::` path); a bundler's path
aliases, a build tag and a macro are not followed, and each language says where it stops. A
test written as a call with a string for its name, such as `test("caps the fee", ...)` in
Jest, has no name an anchor can point at; it is reached through the part markers of
`claim-evidence-names-a-part`, or not at all.

## Cost and risk

**A required dependency.** The tree-sitter runtime and its grammars are MIT-licensed and ship
prebuilt wheels for CPython on Linux, macOS and Windows, but none for musl on ARM64, PyPy or a
free-threaded build. There, installing Irminsul compiles C code and needs a C compiler, and
that reaches adopters whose code is all Python. With the TypeScript, Go and Rust grammars it
installed 6.7 MB. It is required, not an extra: an
extra would let a file resolve on one machine and fail on another, which
`checks-are-deterministic` in [enforcement](../foundation/enforcement.md) rules out, as the
accepted `claim-evidence-names-a-part` already says.

**A grammar's release can rename a node** and break a query, and under decision 4 it can
move every pin of its language. Each grammar and the `tree-sitter` runtime are pinned to one
exact version, so two machines cannot disagree, and each language's queries are tested against a fixture of its code. A
grammar upgrade is a release of Irminsul whose notes say which pins move.

**Every non-Python anchor's pin moves once**, since its hash changes from text to syntax tree
(decision 4), and each is answered by one re-pin after its paragraph is re-read.

**Time.** The probe parsed and queried a small file in 1 to 6 milliseconds, the first query
of a language included. Files are parsed once per run and cached, as Python modules are.

## Decisions

Answered by the owner on 2026-11-27:

1. **TypeScript, Go and Rust are read through tree-sitter, as a required dependency**, as
   `claim-evidence-names-a-part` records. Every adopter installs it, Python-only ones
   included, and builds it from source where no wheel exists. Not chosen: a regular
   expression per language, which needs no dependency but misses nested and multi-line
   definitions; each language's own tool, the most exact, which every machine running the
   gate would need installed.
2. **Python stays on its own parser**, so no Python pin of any adopter moves. Given up: a
   project written for a newer Python than the one running Irminsul can hold files that do
   not parse.
3. **The first languages are TypeScript, Go and Rust.** Whether JavaScript files are read
   through the TypeScript grammar or the JavaScript one is chosen by measuring both on real
   JavaScript; a `.tsx` file is read through the grammar's TSX dialect. Measured on
   2026-11-27: the TSX dialect reads JavaScript too.
4. **A non-Python pin hashes the definition's syntax tree without comments**, as a Python pin
   does. Every existing non-Python pin moves once, and the grammars and the runtime are pinned
   to exact versions so that only a release of Irminsul moves them again. Not chosen: the
   definition's text, which no grammar upgrade moves but which keeps asking about a paragraph
   after a comment edit.
5. **A language is added in this repository**, not by a separate package. Registering one from
   outside is left to a later RFC.
6. **The foundation gains the principle** "A feature that reads code reads it through the
   language interface, so it reaches every language Irminsul reads, and a language is added in
   one place", in the pull request that lands the interface, since it cannot be followed
   before.

Answered by the owner on 2026-11-27, while the tree-sitter readers were built:

7. **A file the grammar cannot read whole answers what parsed.** A definition or an import
   whose own syntax holds no error is answered, and a symbol not found in such a file is
   unreadable, not missing. The grammars lag their languages: of 1,924 TypeScript files of
   real projects 99 held an error to the grammar, 93 of them on the one line
   `importOriginal<typeof import("./api")>()`, and the newest TypeScript grammar dates from
   2024-11. Not chosen: such a file answers nothing, as this RFC first said and as a Python
   file does.
8. **An anchor into TypeScript, Go or Rust names a definition the reader finds.** One to
   anything else, such as a key of an object literal, is `claim-anchor/missing-symbol`, with
   no search of the text for the name. Not chosen: keeping the search until the part markers
   of `claim-evidence-names-a-part` exist, which would have kept every such anchor resolving.
9. **`import-deps` reports a missing import only where every import is placed.** A reading
   says whether every import of its file is placed: a Python file's is, and a Go file's
   under a `go.mod`, when the file parses whole; a TypeScript or a Rust file's never is,
   since a path alias or another crate may stand between two files. A `depends_on` is judged only between docs whose common
   languages have every import of the depending doc's files placed. Not chosen: judging every
   language with a reader, which would report true dependencies with no way to answer.
10. **For TypeScript, every named function a test file defines is offered as a test**, as the
    design detail below says; the reader knows a test file by the test call it holds. Not
    chosen: offering none, since such a function is often a helper.

## Design detail

- **Today, by question.**

  | A feature asks | Where it is answered | Languages |
  |---|---|---|
  | What does this file define, on which lines? | `CodeResolver._symbol_index`, `src/irminsul/code_references.py` | Python |
  | Which text of a definition does a pin hash? | `resolve`, `src/irminsul/anchors.py`: the syntax tree for Python; for any other file, the lines from a definition keyword, whitespace collapsed | Python by tree, others by text |
  | What does this file import? | `imported_paths` and `IMPORT_LANGUAGE`, `src/irminsul/checks/dependency_check.py`, which `Ranker.importers` in `src/irminsul/ranked_tests.py` also calls | Python |
  | Which functions are tests? | the tests `anchors --suggest --doc` offers, `src/irminsul/binding.py`: a name that starts with `test` | Python |
  | Which names does a function body refer to? | the tests `anchors --suggest --doc` offers, `src/irminsul/binding.py` | Python |
  | Which commands, routes, tools and exports does a file declare? | `src/irminsul/inventory/`: Typer, FastAPI and MCP by syntax tree; TypeScript exports, Click, argparse, Flask, cobra, clap, commander and Express by rule | all four |
  | Which environment variables does a file read? | `src/irminsul/inventory/env_vars.py`, one pattern per language | all four |

- **Today, by feature.**

  | Feature | Python | TypeScript | Go | Rust |
  |---|---|---|---|---|
  | A code span is paired with the function or class it names, and its lines | yes | an exported one, its first line only | no | no |
  | The review queue re-asks a sentence naming a changed function | yes | no | no | no |
  | `context <file>` lists the tests that import the file | yes | no | no | no |
  | `anchors --suggest --doc` offers the tests that name a function | yes | no | no | no |
  | `import-deps` checks `depends_on` against imports | yes | no | no | no |
  | An anchor's pin ignores a comment edit | yes | no | no | no |

- **The interface.** One reader per language, answering the five questions for a file's
  text, so a revision read from git is answered the same way. The profile names its reader,
  as `claim-evidence-names-a-part` lets it name a finder; the reader is code and stays out of
  the profile's data. Python's reader wraps today's code; the others share one tree-sitter
  reader that loads the language's grammar and query file. A Rust attribute such as
  `#[derive]` is a sibling of the item it annotates in the grammar, so the reader joins the
  attributes above a definition to its lines, as Python's decorators are. A Python file that
  does not parse answers no definitions and says so, as today; decision 7 says what a file
  tree-sitter cannot read whole answers.
- **Tests, by convention.** Python: a function whose name starts with `test`. Go: a function
  named `Test...` in a `_test.go` file, which a reader given a file's text and not its name
  tells by the function's one `*testing.T` parameter. Rust: a function under `#[test]`.
  TypeScript: a test is a call, not a definition, so only a named function a test file
  defines can be offered.
- **The query file**, for TypeScript, as the probe used it:

  ```
  (function_declaration name: (identifier) @name) @def
  (class_declaration name: (type_identifier) @name) @def
  (method_definition name: (property_identifier) @name) @def
  (lexical_declaration (variable_declarator name: (identifier) @name value: (arrow_function))) @def
  (import_statement source: (string) @import)
  ```

- **The part finder of `claim-evidence-names-a-part`** is this interface's canonical text:
  that RFC lets a language profile declare a finder for its extensions and records
  tree-sitter as the route once several languages need one. One hook serves both, not two.
- **What lifts when it lands.** Decision 6 of
  [the RFC that re-asks sentences naming changed code](a-change-re-asks-the-sentences-that-name-its-code.md)
  and the sentence of
  [the RFC on anchoring to tests](a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts.md)
  that tests in another language are not offered yet. The loop's wording drops "Python".
- **Records this changes.** `surface-rules-and-language-profiles-are-data` decides "The
  reader is not a profile field, because a profile is data" and that `import-deps` reads
  Python: a profile stays data and names its reader, which is code, and `import-deps` reads every
  language that answers imports. `code-is-named-in-code-spans-and-bound-by-anchors` decides
  how a pin is hashed.
- **Wheels.** `tree-sitter` 0.26.0 has wheels for CPython 3.10 to 3.14 on Linux (glibc on
  x86-64 and ARM64, musl on x86-64), macOS and Windows, and none for musl on ARM64, PyPy or a
  free-threaded build. Each grammar package ships one wheel per platform that serves every
  CPython but a free-threaded build, and `tree-sitter-typescript` has none for musl on ARM64.
- **Measured** on 2026-11-26 with `tree-sitter` 0.26.0, `tree-sitter-typescript` 0.23.2,
  `tree-sitter-go` 0.25.0 and `tree-sitter-rust` 0.24.2 on CPython 3.12: installed sizes 2.0,
  3.1, 0.3 and 1.3 MB; one small file per language parsed and queried in 5.9, 0.8 and 2.8 ms.
- **Not chosen.** A regular expression per language, and each language's own toolchain:
  decision 1 says why. Moving Python onto tree-sitter: decision 2.

## Requirements

### Requirement: A definition in a supported language is found with its lines
ID: definitions-in-every-supported-language
Provenance: code

For a file of Python, TypeScript, Go or Rust, the language's reader SHALL return each
function, class or type and each method, with its name, the type that holds it, and its first
and last line.

#### Scenario: A TypeScript function
- **WHEN** `src/fees.ts` holds `export function lateFee()` on lines 2 to 4
- **THEN** the reader returns `lateFee` with lines 2 to 4

#### Scenario: A Go method
- **WHEN** `desk.go` holds `func (d *Desk) CheckOut(id string) string` on line 7
- **THEN** the reader returns `CheckOut`, held by `Desk`, on line 7

### Requirement: A feature that reads code names no language
ID: features-read-code-through-the-interface
Provenance: code

Binding a code span, the review queue's touched code, a packet's tests, the tests
`anchors --suggest` offers, `import-deps` and anchor pins SHALL read definitions and imports
through the language's reader.

#### Scenario: A changed TypeScript function
- **WHEN** a change edits the body of `lateFee` in `src/fees.ts`, and a guide names `` `lateFee()` `` in a sentence the change does not edit
- **THEN** `list review --changed` queues that sentence, marked `names-changed-code`

### Requirement: A language is added in one place
ID: a-language-is-added-in-one-place
Provenance: code

A language SHALL be added by its profile, its grammar and its query file, with no change to a
check.

#### Scenario: A language no check names
- **WHEN** a test registers a profile, a grammar and a query file for a language no check names
- **THEN** a code span naming a function in a file of that language is paired with it

## Tasks

- `T1` Add the interface, with Python's answers from its parser and no change in behaviour. (req: definitions-in-every-supported-language)
- `T2` Move the five modules that call Python's parser for these questions onto the interface: `code_references.py`, `anchors.py`, `binding.py`, `ranked_tests.py` and `checks/dependency_check.py`. (req: features-read-code-through-the-interface)
- `T3` Add tree-sitter as a required dependency, with readers and query files for TypeScript, Go and Rust and a fixture each, `.tsx` read through the TSX dialect, and the grammar for JavaScript files chosen by measuring both on real JavaScript. (req: definitions-in-every-supported-language)
- `T4` Hash a non-Python pin from its syntax tree, pin the runtime and grammars exactly, and say how an adopter answers the moved pins. (component: anchors)
- `T5` Move the environment variable pattern into the profile, and say in the languages doc how a language is added. (req: a-language-is-added-in-one-place)
- `T6` Lift the Python-only sentences the two implemented RFCs left in the loop, the component docs and the records, and state the rules in the records; the sealed RFCs stay as they are. (component: languages)
- `T7` Add the principle of decision 6 to `docs/foundation/principles.md` in the pull request that lands the interface. (component: languages)

## Resolution

Accepted by the owner on 2026-11-27, with the answers recorded under Decisions, and resolved by
[Surface rules and language profiles are data](../decisions/surface-rules-and-language-profiles-are-data.md),
whose Changes item records it. [Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)
records its part too, how a pin is hashed. Each rule joins its record's Decision with the
implementation, as an edit in place.
