---
id: anchors
title: Anchored prose claims
status: stable
summary: Anchored prose claims pinned to code.
describes:
  - src/irminsul/anchors.py
  - src/irminsul/binding.py
depends_on:
  - docgraph
  - frontmatter
  - surface
owns_tests:
  - tests/test_binding.py
  - tests/test_cli_anchors.py
implements:
  - acknowledge-a-reviewed-co-change-or-evidence-drift
---

# Anchored prose claims

This component pins a prose claim to the code it describes. Where `mtime-drift` asks
the blunt question "did anything under this doc change?", an anchor asks the precise
one: "did *this symbol* change since this paragraph was last verified?"

## How it stays precise

A paragraph carries an inline marker naming a file and (optionally) a symbol, plus a
content hash. In a Python file the hash is taken over the **syntax tree** of the symbol's
definition, not its raw text: `_canonical` writes out each node's type and fields, never
its position, so reformatting or editing comments does not trip the claim, while a
docstring edit or any other real change to the code does. That text depends on the tree
alone, not on how an interpreter prints code, so a pin written on one Python version holds
on every version that parses the code to the same tree, as a CI matrix needs
([Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)).
A name is bound by a function, a class, or
an assignment, so a threshold or a registry can be anchored as readily as a function,
and a constant's hash covers its whole assignment statement: two names bound by one
`A, B = ...` share a hash, and an edit to either re-asks both claims. In a file of any
other language the symbol resolves by name as a whole token, and the hash covers the
block that starts at the line defining it, with whitespace normalized. A marker written
inside a code span or a fenced block is an example and is not read, so this syntax can
be documented without the example becoming a live anchor.
<!-- anchor: src/irminsul/anchors.py#resolve @sha256:c3f4df66e0c1 -->
<!-- anchor: src/irminsul/anchors.py#_find_symbol @sha256:95c45a01a21c -->
<!-- anchor: src/irminsul/anchors.py#_canonical @sha256:1c9d471d4bfc -->

## Binding the code a doc names

A code span such as `fetchUserSession()` names code, but which file defines it is a
judgment ([Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)).
A code name that no surface, symbol index, or repository path resolves, and no anchor in
the doc binds, is unbound, unless an enabled language defines it itself, as Python does
`IndexError` (the profile's `builtins`): that name is the language's, not this repository's,
and is never listed. `irminsul list review --changed` shows a changed sentence's
unbound names, and `irminsul anchors --suggest` lists every one in live docs, or in one
doc with `--doc`, with the places an anchor could point and the marker to paste. It
writes nothing: the agent picks the file. A Python definition inside a function or a
block, which no anchor can name, is listed as such rather than dropped, so a name the
code defines is never answered with "no source file contains it".

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
that narrow form. A `--doc` or a selector that names
nothing exits 2 and writes nothing, because re-pinning nothing would read as success.
<!-- anchor: src/irminsul/anchors.py#repin_doc @sha256:a335249a82a0 -->

## Scope & Limitations

Anchors are opt-in — only paragraphs that carry a marker are checked; everything else
stays on the coarse mtime net. Outside Python a symbol resolves by name, so a name left
in a string or a trailing comment still resolves, and the block hash re-flags a claim for
any edit inside the block. `--suggest` searches the configured source roots only, read
from the graph's [source tree](docgraph.md), and a check resolves an anchor through that
tree's [`SourceReader`](surface.md), so a file many anchors name is read and parsed once
per run. An anchor proves the *code* has not changed since the claim was pinned; it
cannot prove the prose was *correct* when pinned — that judgement remains human. It
covers only the symbol it names: a paragraph anchored to one function says nothing about
a second function the same paragraph describes, and a behaviour changed through code no
anchor names is not seen. Anchoring each name a paragraph depends on is the answer;
nothing derives that set.

## Implemented requirements

- **acknowledge-a-reviewed-co-change-or-evidence-drift#re-pin-writes-claim-pins** — `irminsul anchors --re-pin --doc <doc>` SHALL write the current normalized hash of every evidence file of every claim in that doc, and SHALL drop a pin on a path the claim no longer cites. (provenance: code; [RFC](../rfcs/acknowledge-a-reviewed-co-change-or-evidence-drift.md))
  <!-- anchor: src/irminsul/anchors.py#repin_claims @sha256:b7fbcd86889c -->
