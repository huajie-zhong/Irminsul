---
id: anchors
title: Anchored prose claims
audience: explanation
tier: 3
status: stable
depends_on: []
describes:
  - src/irminsul/anchors.py
tests:
  - tests/test_checks_claim_anchor.py
---

# Anchored prose claims

This component pins a prose claim to the code it describes. Where `mtime-drift` asks
the blunt question "did anything under this doc change?", an anchor asks the precise
one: "did *this symbol* change since this paragraph was last verified?"

## How it stays precise

A paragraph carries an inline marker naming a file and (optionally) a symbol, plus a
content hash. The hash is taken over the symbol's **AST-normalized** body, not its
raw text, so reformatting or editing comments does not trip the claim — only a real
change to the code does. Resolution supports a top-level name or a dotted
`Class.method`.
<!-- anchor: src/irminsul/anchors.py#resolve @sha256:71f7b0a1af45 -->

The pin is a deliberate acknowledgement, not an automatic one: refreshing it with
`irminsul anchors --re-pin` is how an author says "I re-read this and it is still
true." Nothing rewrites a pin silently, because that would rubber-stamp the very
staleness the anchor exists to catch.

## Scope & Limitations

Anchors are opt-in — only paragraphs that carry a marker are checked; everything else
stays on the coarse mtime net. Symbol resolution is Python-only for now (other
languages can reuse the same marker once their extractor lands). An anchor proves the
*code* has not changed since the claim was pinned; it cannot prove the prose was
*correct* when pinned — that judgement remains human.
