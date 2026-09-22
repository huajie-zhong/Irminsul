---
id: anchors
title: Anchored prose claims
status: stable
depends_on: []
describes:
  - src/irminsul/anchors.py
  - src/irminsul/binding.py
owns_tests:
  - tests/test_binding.py
  - tests/test_cli_anchors.py
---

# Anchored prose claims

This component pins a prose claim to the code it describes. Where `mtime-drift` asks
the blunt question "did anything under this doc change?", an anchor asks the precise
one: "did *this symbol* change since this paragraph was last verified?"

## How it stays precise

A paragraph carries an inline marker naming a file and (optionally) a symbol, plus a
content hash. In a Python file the hash is taken over the symbol's **AST-normalized**
body, not its raw text, so reformatting or editing comments does not trip the claim —
only a real change to the code does, and resolution supports a top-level name or a
dotted `Class.method`. In a file of any other language the symbol resolves when its
name appears as a whole token, and the hash covers the indented block that starts at
the line defining it, with whitespace normalized: a line with a definition keyword such
as `func` or `class`, or an assignment, else its first mention outside a comment. A
dotted name is looked for after its parent's first mention, a brace on the line after a
signature stays in the block, and a file that is not UTF-8 does not resolve. A marker
written inside a code span is an example and is not read.
<!-- anchor: src/irminsul/anchors.py#resolve @sha256:6c8fc06b0650 -->

## Binding the code a doc names

A code span such as `fetchUserSession()` names code, but which file defines it is a
judgment ([anchors bind code names in any language](../decisions/anchors-bind-code-names-in-any-language.md)).
A span can only be a code name when it is a call, a dotted name, or an identifier with
an underscore or a lowercase-to-uppercase change. When no surface, symbol index, or
repository path resolves it and no anchor in the doc binds it, it is unbound.
`irminsul list review --changed` lists a changed sentence with its unbound names, and
`irminsul anchors --suggest` lists every unbound name in live docs, or in one doc with
`--doc`, with up to three source files that contain it, definition-like lines first, and
the marker to paste. The command writes nothing: the agent picks the file.

The pin is a deliberate acknowledgement, not an automatic one: refreshing it with
`irminsul anchors --re-pin` is how an author says "I re-read this and it is still
true." The same command re-pins the `fingerprints` of watched inventory surfaces.
Nothing rewrites a pin silently, because that would rubber-stamp the very
staleness the anchor exists to catch. That claim is per-document, so `--re-pin`
requires `--doc <path>`: nobody re-reads a whole repository at once, and the
command used to sweep every doc whatever `--doc` said. `--all` re-pins everything
for the rare case that is really what happened, such as a formatting-only sweep.

## Scope & Limitations

Anchors are opt-in — only paragraphs that carry a marker are checked; everything else
stays on the coarse mtime net. Outside Python a symbol resolves by name, so a name left
in a comment still resolves, and the block hash re-flags a claim for any edit inside
the block. `--suggest` searches the configured source roots only. An anchor proves the
*code* has not changed since the claim was pinned; it cannot prove the prose was
*correct* when pinned — that judgement remains human. It covers only the symbol it
names: a paragraph anchored to one function says nothing about a second function the
same paragraph describes, and a behaviour changed through code no anchor names is not
seen. Anchoring each name a paragraph depends on is the answer; nothing derives that set.
