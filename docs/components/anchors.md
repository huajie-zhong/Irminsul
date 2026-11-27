---
id: anchors
title: Anchored prose claims
status: stable
describes:
  - src/irminsul/anchors.py
  - src/irminsul/binding.py
depends_on:
  - checks
  - context
  - docgraph
  - frontmatter
  - languages
  - surface
owns_tests:
  - tests/test_binding.py
  - tests/test_cli_anchors.py
summary: Anchored prose claims pinned to code.
implements:
  - acknowledge-a-reviewed-co-change-or-evidence-drift
  - a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts
  - a-pin-that-no-longer-matches-its-file-is-listed
---

# Anchored prose claims

This component pins a prose claim to the code it describes. Where `mtime-drift` asks
the blunt question "did anything under this doc change?", an anchor asks the precise
one: "did *this symbol* change since this paragraph was last verified?"

## How it stays precise

A paragraph carries an inline marker naming a file and (optionally) a symbol, plus a
content hash. `resolve` asks the [reader](languages.md#readers) of the file's language for
the canonical text of the symbol's definition and hashes that, which is why this component
depends on `languages`. In a Python file it is the
**syntax tree** of the definition, not its raw text: `_canonical` writes out each node's type and fields, never
its position, so reformatting or editing comments does not trip the claim, while a
docstring edit or any other real change to the code does. That text depends on the tree
alone, not on how an interpreter prints code, so a pin written on one Python version holds
on every version that parses the code to the same tree, as a CI matrix needs
([Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)).
A name is bound by a function, a class, or
an assignment, so a threshold or a registry can be anchored as readily as a function,
and a constant's hash covers its whole assignment statement: two names bound by one
`A, B = ...` share a hash, and an edit to either re-asks both claims. In a TypeScript,
JavaScript, Go or Rust file it is the tree the language's grammar gives, written without
its comments and without the layout a formatter chooses, such as a line break or a trailing comma
([languages](languages.md#typescript-javascript-go-and-rust)). In each of these a symbol
is a definition the reader finds, and no search of the text for its name stands in for
one: a symbol the reader does not find is missing, or unreadable when the file holds
syntax its grammar could not read, since the symbol may be in that part. In a file no
reader reads, the symbol resolves by name as a whole token, and the hash covers the
block that starts at the line defining it, with whitespace normalized. A marker written
inside a code span or a fenced block is an example and is not read, so this syntax can
be documented without the example becoming a live anchor.
<!-- anchor: src/irminsul/anchors.py#resolve @sha256:cf3b307eb8a4 -->
<!-- anchor: src/irminsul/languages/python_reader.py#_find_symbol @sha256:95c45a01a21c -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_a_pinned_function_is_clean_after_an_edit_to_its_comment @sha256:cf966b0ec2fb -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_an_anchor_to_a_local_variable_is_a_missing_symbol @sha256:a6f75928ea67 -->
<!-- anchor: tests/test_languages_typescript_reader.py#test_an_absent_name_is_unreadable_in_a_file_that_did_not_parse @sha256:e36c635aa9d0 -->
<!-- anchor: src/irminsul/languages/python_reader.py#_canonical @sha256:1c9d471d4bfc -->

## Binding the code a doc names

A code span such as `fetchUserSession()` names code, but which file defines it is a
judgment ([Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)).
A code name that no surface, symbol index, or repository path resolves, and no anchor in
the doc binds, is unbound, unless an enabled language defines it itself, as Python does
`IndexError` (the profile's `builtins`): that name is the language's, not this repository's,
and is never listed. `irminsul list review --written` shows a written sentence's
unbound names, and `irminsul anchors --suggest` lists every one in live docs, or in one
doc with `--doc`, with the places an anchor could point and the marker to paste. It
writes nothing: the agent picks the file. A definition inside a function or a
block, which no anchor can name, is listed as such rather than dropped, so a name the
code defines is never answered with "no source file contains it".

A dotted span that ends in a file's suffix names a file, not code, so it is never a code
name: `ledger.mts` ends in a suffix a [language profile](languages.md) lists, whichever
language is enabled, and `setup.cfg` in one of the suffixes of files no profile reads that
`code_name` keeps itself.
<!-- anchor: tests/test_binding.py#test_a_file_name_of_any_registered_language_is_not_a_code_name @sha256:49c8c1874620 -->

## Offering the test that asserts a sentence

A sentence that says what code does is best anchored to the test that asserts it: it is
asked about when that test changes, and the test fails when the code stops doing what the
sentence says, where an anchor to the function is asked about on every edit to it
([Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)).
A test function is a definition in a file, so an anchor names it, pins it and drifts with
it like any other. To find one, `irminsul anchors --suggest --doc <doc>` also lists each
code span of that doc that resolves to one function or class, once for each
definition, so two methods of one name in one file are two rows, with where it is
defined and up to three test functions that name it, ordered by path and line, each as a
marker to paste. `naming_tests` asks each test file's [reader](languages.md#readers) which
of its functions are tests, for Python one whose name starts with
`test`, at the top level of a file or in a class there, however deep the classes
nest, and for the other languages as [their reader](languages.md#typescript-javascript-go-and-rust)
says, in a file under
`paths.test_roots` that imports the defining module, which is the reading
`Ranker.importers` makes for the [context packet](context.md#which-tests-a-source-file-gets).
It names the definition when its body refers to it through an import of that module, in
the file or in the test's own body, each import resolved to files by that reader as the
[import checks](checks.md) resolve it (`_names`): a function or class at the top level of its
module by a name imported from it, under an alias too, that the test does not bind itself
as a parameter, a fixture or a local variable, or as an attribute of a name bound to the
module itself; a method by an attribute of its name, in a test whose imports reach its
class or its module. A name no test names is listed and said to have none, the closing
line counts these names apart from the unbound ones, and the JSON gains a list `resolved`
beside `unbound`. Without `--doc` the command lists the unbound names alone.
<!-- anchor: tests/test_binding.py#test_suggest_offers_the_test_that_calls_a_function_the_doc_names @sha256:94b5c37f7a7b -->
<!-- anchor: tests/test_binding.py#test_suggest_offers_at_most_three_tests_by_path_and_line @sha256:5b74b5ae3195 -->
<!-- anchor: tests/test_binding.py#test_suggest_says_so_when_no_test_names_the_definition @sha256:a96352d4b56f -->
<!-- anchor: tests/test_binding.py#test_suggest_without_a_doc_lists_unbound_names_and_no_test @sha256:f01f47ab26b4 -->
<!-- anchor: tests/test_binding.py#test_suggest_lists_two_methods_of_one_name_in_one_file @sha256:80050085aed1 -->
<!-- anchor: tests/test_binding.py#test_a_test_names_a_definition_through_an_import_of_its_module @sha256:a6e3bf78495a -->
<!-- anchor: tests/test_binding.py#test_a_name_the_test_binds_itself_does_not_name_the_definition @sha256:ad1bee32b830 -->
<!-- anchor: tests/test_binding.py#test_a_method_is_named_by_a_test_whose_file_imports_its_class @sha256:3b01720c19d0 -->

The command runs nothing, so an offered test is one that names the function, not one
known to assert the sentence. Whoever pastes its marker first changes the code so the
sentence is false and sees that test fail, the second step of
[tying a sentence to a test](../guides/agent-protocol.md#tying-a-sentence-to-a-test).

## Re-pinning is an acknowledgement

The pin is a deliberate acknowledgement, not an automatic one: refreshing it with
`irminsul anchors --re-pin` is how an author says "I re-read this and it is still
true." Nothing rewrites a pin silently, because that would rubber-stamp the very
staleness the anchor exists to catch. The same command pins each evidence file of every
claim in the doc under the claim's `pinned`, with the hash a file-level anchor would
take, so `claim-provenance/evidence-drift` does not re-ask a re-read claim over a
formatting-only commit; a pin only ever removes drift. A doc cited as evidence is hashed with
its own pins left out (`file_pin`, through `without_pins`), so re-pinning an anchor in that
doc does not re-ask the claims citing it, while a change to its words still does.

The acknowledgement is per document, so `--re-pin` requires `--doc <id|path>`: nobody
re-reads a whole repository at once, and `--all` is for the rare case that is really what
happened, such as a formatting-only sweep or a move to a new pin format. A re-read is rarely of a whole doc either, so
`--claim` and `--anchor` narrow a re-pin to what was re-read, `--evidence` narrows a claim
to one of its evidence files, and the `evidence-drift` and `claim-anchor` suggestions print
that narrow form. An `evidence-drift` finding names every evidence file of its claim that
changed after the doc, and its suggestion gives each one `--evidence`, so a pin of the claim's
other evidence that no longer matches, which the finding did not ask about, is left for its
own re-read. A `--doc` or a selector that names
nothing exits 2 and writes nothing, because re-pinning nothing would read as success.
<!-- anchor: src/irminsul/anchors.py#repin_doc @sha256:a335249a82a0 -->
<!-- anchor: tests/test_cli_anchors.py#test_the_evidence_drift_suggestion_re_pins_only_the_evidence_it_names @sha256:4de675f9c06d -->

## Listing the pins that no longer match

`irminsul anchors --stale` lists every pin that no longer matches what it pins, in every doc
or the one `--doc` names: each anchor whose target resolves and hashes differently from its
pin, and each pin of a claim's evidence whose file does. `stale_pins` reads each through
`resolve` and `file_pin`, as `--re-pin` reads it, so nothing a re-pin just wrote is listed,
and a target that does not resolve is left to the findings that report it. A row names the
doc and the line of the anchor marker, or of the claim's `<!-- claim:<id> -->` marker, or 1
when no paragraph declares the claim; the pin and the current hash; and the `--re-pin`
command narrowed to that pin, each argument shell-quoted so it runs as printed:
`--claim <id> --evidence <path>`, which moves that pin alone, or `--anchor <path#symbol>`,
which also moves any other anchor of the doc with the same `path#symbol`, since `--anchor`
names a target. Plain output prints one row per line and a count, and `--format json` prints
`{"version": 1, "stale": [...]}`. It writes nothing and exits 0, since the checks are the gate
([Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)),
and with `--re-pin` or `--suggest` it exits 2 and writes nothing: one action per run.
<!-- anchor: src/irminsul/anchors.py#stale_pins @sha256:ffb7528712e8 -->
<!-- anchor: tests/test_cli_anchors.py#test_stale_lists_a_component_claims_changed_evidence @sha256:fc748e708176 -->
<!-- anchor: tests/test_cli_anchors.py#test_stale_lists_nothing_when_every_pin_matches @sha256:266cf2aec24d -->
<!-- anchor: tests/test_cli_anchors.py#test_stale_with_another_action_exits_2_and_writes_nothing @sha256:f4c0c567ab07 -->
<!-- anchor: tests/test_cli_anchors.py#test_an_anchor_whose_target_no_longer_resolves_is_not_listed @sha256:4af54ba20883 -->
<!-- anchor: tests/test_cli_anchors.py#test_the_re_pin_of_a_row_runs_as_printed_when_a_path_holds_a_space @sha256:b11810f0ea13 -->

A pin can be stale with no check asking about it. `claim-provenance/evidence-drift` judges
the claims of the foundation and architecture layers alone, and reads a pin that no longer
matches as no pin, falling back to commit times, so a doc committed after its evidence hides
it ([checks](checks.md)). Each row's `reported_by` says which: the listing runs whichever of
`claim-anchor` and `claim-provenance` `checks.enabled` enables, over the same graph, so it
names only a finding `irminsul check` reports: `claim-anchor/pinned-drift` for a stale
anchor, `claim-provenance/evidence-drift` for each evidence file of a claim that the finding
names, and null for a pin no finding names, such as a second stale pin of a claim whose
finding names only the evidence that changed after the doc.
<!-- anchor: src/irminsul/anchors.py#StalePin.reported_by @sha256:a0876d8fce1b -->
<!-- anchor: tests/test_cli_anchors.py#test_only_the_evidence_a_drift_finding_names_is_reported_by_it @sha256:0a8f078dddec -->
<!-- anchor: tests/test_cli_anchors.py#test_stale_lists_a_changed_anchor_with_its_finding @sha256:88b2549e0dd3 -->
<!-- anchor: tests/test_cli_anchors.py#test_every_evidence_file_a_drift_finding_names_is_reported_by_it @sha256:1141f4a7bfa1 -->
<!-- anchor: tests/test_cli_anchors.py#test_reported_by_names_only_a_finding_of_an_enabled_check @sha256:cf7e9b2ad0eb -->

## Scope & Limitations

Anchors are opt-in — only paragraphs that carry a marker are checked; everything else
stays on the coarse mtime net. In a file no reader reads, such as a config file or
code of a language without a reader, a symbol resolves by name, so a name left
in a string or a trailing comment still resolves, and the block hash re-flags a claim for
any edit inside the block. `--suggest` searches the configured source roots for
definitions, and under `--doc` the declared test roots for the tests that name them, each
read from the graph's [source tree](docgraph.md), and a check resolves an anchor through that
tree's [`SourceReader`](surface.md), so a file many anchors name is read and parsed once
per run. An anchor proves the *code* has not changed since the claim was pinned; it
cannot prove the prose was *correct* when pinned — that judgement remains human. It
covers only the symbol it names: a paragraph anchored to one function says nothing about
a second function the same paragraph describes, and a behaviour changed through code no
anchor names is not seen. Anchoring each name a paragraph depends on is the answer;
nothing derives that set.

`--stale` lists pins and fails nothing: a pin it lists stays stale until someone re-reads
the prose and re-pins it, and no gate asks whether anyone ran it. It reads only what is
pinned, so an unpinned anchor or evidence entry is not listed, nor a pin on a path its claim
no longer cites, which nothing reads. A drift finding carries no target, claim or evidence
field, so `reported_by` is read from its message, where a quoted name ends at the first `'`:
a pin whose path or claim id holds one is reported by nothing. The MCP `anchors` tool
returns `claim-anchor` findings and has no such listing.

The tests `--suggest --doc` offers are found in the syntax tree, and nothing is run. A
test that reaches the function through a helper, a fixture or the command line is not
offered. A method is still found by name, since the tree does not say what class an
object has: a test whose file imports `Answer` and reads `finding.line` is offered for
`Answer.line`, and one that reads `load_graph(root).guidance_files` with no import of
`DocGraph` or its module is not offered for `DocGraph.guidance_files`. A name bound
anywhere in a test's body, a function nested in it included, counts as the test's own
throughout it, which can leave out a test that names the definition and never adds one
that does not. The three listed are the first by path and line, which for a widely used
class need not be the three that say most. Only test files under `paths.test_roots` are
read, in a language a reader reads, and with no test root declared the listing says that no
test file was read. Nothing measures how much of a function its tests guard.

## Implemented requirements

- **acknowledge-a-reviewed-co-change-or-evidence-drift#re-pin-writes-claim-pins** — `irminsul anchors --re-pin --doc <doc>` SHALL write the current normalized hash of every evidence file of every claim in that doc, and SHALL drop a pin on a path the claim no longer cites. (provenance: code; [RFC](../rfcs/acknowledge-a-reviewed-co-change-or-evidence-drift.md))
  <!-- anchor: src/irminsul/anchors.py#repin_claims @sha256:b7fbcd86889c -->
- **a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts#suggest-offers-the-tests-of-a-definition** — `irminsul anchors --suggest --doc <doc>` SHALL list each code span of that doc that resolves to one function or class, with up to three test functions, in files under the configured test roots that import the defining module, whose body names that definition through the file's imports, each as an anchor marker ready to paste. A name the test binds itself SHALL NOT count as naming the definition. Without `--doc` it SHALL list what it lists today. The function or class and its tests are of any language a reader reads: the RFC offered Python's alone, and [Each language reads its code through one interface](../rfcs/each-language-reads-its-code-through-one-interface.md) widened it. (provenance: code; [RFC](../rfcs/a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts.md))
  <!-- anchor: src/irminsul/binding.py#naming_tests @sha256:a48e8aeceb91 -->
  <!-- anchor: tests/test_binding.py#test_suggest_offers_the_test_that_calls_a_function_the_doc_names @sha256:94b5c37f7a7b -->
  <!-- anchor: tests/test_binding.py#test_a_name_the_test_binds_itself_does_not_name_the_definition @sha256:ad1bee32b830 -->
  <!-- anchor: tests/test_binding.py#test_suggest_says_so_when_no_test_names_the_definition @sha256:a96352d4b56f -->
  <!-- anchor: tests/test_binding.py#test_suggest_without_a_doc_lists_unbound_names_and_no_test @sha256:f01f47ab26b4 -->
  <!-- anchor: tests/test_languages_typescript_reader.py#test_suggest_offers_the_test_function_that_calls_late_fee @sha256:296622051fe4 -->
  <!-- anchor: tests/test_languages_go_reader.py#test_suggest_offers_the_test_that_calls_late_fee_for_the_guide_sentence @sha256:697d9eb5462f -->
  <!-- anchor: tests/test_languages_rust_reader.py#test_suggest_offers_the_integration_test_that_calls_the_function_a_guide_names @sha256:6ed061e33ad5 -->
- **a-pin-that-no-longer-matches-its-file-is-listed#stale-pins-are-listed** — `irminsul anchors --stale` SHALL list each anchor and each claim evidence pin, in every doc or the one `--doc` names, whose target's current hash differs from its pin, each with the command that re-pins only that pin, or that pin and the other anchors of its doc that name the same target, and SHALL exit 0. (provenance: code; [RFC](../rfcs/a-pin-that-no-longer-matches-its-file-is-listed.md))
  <!-- anchor: src/irminsul/anchors.py#stale_pins @sha256:ffb7528712e8 -->
  <!-- anchor: tests/test_cli_anchors.py#test_stale_lists_a_component_claims_changed_evidence @sha256:fc748e708176 -->
  <!-- anchor: tests/test_cli_anchors.py#test_stale_lists_nothing_when_every_pin_matches @sha256:266cf2aec24d -->
  <!-- anchor: tests/test_cli_anchors.py#test_stale_with_another_action_exits_2_and_writes_nothing @sha256:f4c0c567ab07 -->
  <!-- anchor: tests/test_cli_anchors.py#test_anchors_that_share_a_target_are_each_listed_with_one_re_pin @sha256:0a3dea875ed1 -->
