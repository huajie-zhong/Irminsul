---
id: code-is-named-in-code-spans-and-bound-by-anchors
title: Code is named in code spans and bound by anchors
status: stable
describes: []
summary: A code span is a literal mention checked against the tree, a bare `.md` name in plain text must be a link, and an anchor binds a paragraph to the definition it describes, pinned by a hash of its syntax tree; unbound names are queued for review.
governs:
  - src/irminsul/anchors.py
  - src/irminsul/binding.py
  - src/irminsul/code_references.py
  - src/irminsul/checks/code_references.py
  - src/irminsul/checks/code_spans.py
  - src/irminsul/checks/file_paths.py
  - src/irminsul/checks/prose_file_reference.py
  - src/irminsul/checks/claim_anchor.py
  - src/irminsul/cli.py#anchors_command
  - src/irminsul/cli.py#_repin_scope_problem
  - src/irminsul/cli.py#_re_pin
  - src/irminsul/cli.py#_suggest_anchors
retires:
  - id: prose-file-reference-own-markers
    kind: concept
    matches:
      - ignore-end-without-start
      - ignore-start-without-end
      - stale-suppression
    guidance: The check has no markers of its own; put a literal mention in a code span, and answer `code-references/unknown-path` with `<!-- irminsul:ignore code-references reason="..." -->`.
---

# Code is named in code spans and bound by anchors

## Status

Accepted, 2026-10-28.

## Context

A doc that names `fetchUserSession()` goes stale when the function is renamed, and a tool that
cannot tell which function the doc meant cannot report it. Deciding which file a name refers to
is judgment made once; checking that the file still defines it is mechanical, forever. A `.md`
name in plain text outside a link is provably a link nobody wrote, but in a code span it is
usually an example never meant to resolve, and a suppression grammar kept for those examples
disagreed with the shared ignore comment.

A pin is written on one machine and compared on another, often a CI leg on a different
Python. The hash was taken over `ast.unparse`, and how `ast.unparse` prints one tree changes
between patch releases: 3.12.3, the system Python of GitHub's Ubuntu runner, prints an
f-string with nested quotes differently from 3.12.10 and later. CI reported
`claim-anchor/pinned-drift` on two anchors no local run reported, and fifteen claim pins of
this repository quietly fell back to the commit-time comparison. Two smaller dependences sat
under the printer: the 3.12.3 parser closes a format spec such as `{x:{w}}` with an empty
literal, and `repr` escapes a character or not by the interpreter's Unicode version.

A claim's pin covers a whole file, so an edit anywhere in it re-asks the claim: one claim
citing `docs/components/checks.md` was re-asked 31 times in a week for edits to unrelated
paragraphs, which trains a reader to re-pin without reading.

## Decision

- **A code span is a literal mention.** `prose-file-reference/unlinked-reference`, certain,
  reports a `.md` name in plain text outside a link; it does not read code spans or fenced
  blocks, and keeps no markers.
- **A backticked path is checked against the tree.** `code-references/unknown-path`, a hint,
  reports an inline code span in a stable doc outside the decisions and rfcs layers, or in a
  `paths.extra_docs` file, that is written like a path and names no file. Written like a path:
  no whitespace, `*` or `://`, and a `/` before a last segment with an extension of letters and
  digits, or a bare name ending `.md`, `.toml`, `.yml`, `.yaml`, `.json` or an enabled
  language's suffix. Named: a file git lists, a source or test file, or a file on disk outside
  `.git` and dependency directories, whose path equals the span or ends with `/` and the span;
  or the file the span reaches from its doc's directory. An example takes
  `<!-- irminsul:ignore code-references reason="..." -->`. A span that invokes a command or
  option the CLI does not declare is certain; one naming a function or environment variable no
  source defines or reads is a hint.
- **An anchor binds a paragraph to code.** `<!-- anchor: path#symbol -->` names the file and
  symbol a paragraph describes; `claim-anchor/missing-file` and `missing-symbol` are certain,
  `pinned-drift` and `unpinned` hints. A Python file resolves a symbol through its syntax tree,
  at the top level or as `Class.member`. Another text file resolves a symbol whose every dotted
  part appears as a whole token, and pins the whitespace-normalized block at its defining line.
  A file anchor pins the whole file. A span resolves with or without a trailing `()`.
- **A Python pin hashes `_canonical` of the tree** in `src/irminsul/anchors.py`: each node's
  type name and its fields from `ast.iter_fields`, nodes and lists recursively, leaves through
  `ascii`. Positions are never written, a field that is `None` or `[]` is left out, and an
  empty literal inside an f-string is dropped. The pin is the first 12 hex digits of the
  sha256 of that text, for a symbol anchor, a file anchor and a claim evidence pin alike.
- **What a pin covers does not change.** A docstring edit drifts a Python pin; a comment or a
  reformat does not. Anchors into other languages keep the whitespace-normalized text.
- **A re-pin records a re-read.** `irminsul anchors --re-pin --doc <doc>`, narrowed by
  `--claim`, `--evidence` or `--anchor`, writes a claim's `pinned` map of evidence path to
  normalized hash. A pin on a path the claim no longer cites is dropped by the next re-pin.
  `irminsul fix` never re-pins.
- **Unbound names are queued, not failed.** Under `list review --changed`, a span in an edited
  sentence that names code distinctively, as `name()` or a dotted, snake_case or camelCase
  identifier, which nothing resolves and no anchor in the doc binds, is marked `unbound-name`.
- **Suggestions name only what an anchor can reach.** `irminsul anchors --suggest` lists each
  unbound name with up to three places and the marker to paste. A Python definition comes from
  the syntax tree under the dotted path an anchor accepts; one inside a function or block is
  listed as out of reach rather than dropped; a file that only mentions the name is offered
  only when nothing defines it. The agent chooses and writes the anchor.
  <!-- anchor: src/irminsul/binding.py#suggest @sha256:c38ecde76ec0 -->
- **Framework extractors stay** as precision for the kinds they know, such as an option checked
  against its own command.
- **Claim evidence and anchors name a part of a file** (accepted, not yet implemented):
  - An evidence entry may name a part as `path#part`, one part per entry, and its pin covers
    only that part.
  - A finder chosen by the file's extension locates the part without guessing: a definition in
    Python, a heading's section in Markdown, a dotted key in TOML, YAML and JSON, and the lines
    between `irminsul:part <name>` and `irminsul:end <name>` markers in any text file. A marker
    wins over a same-named symbol, heading or key. A name that is ambiguous, unclosed or absent
    does not resolve, and an entry that does not resolve is certain.
  - A Python part, marked or defined, is hashed through its syntax tree, as every Python pin
    is, so a comment edit does not re-ask it; a marked Python region that does not parse on its
    own does not resolve.
  - Anchors resolve through the same finders, and the guess that located a non-Python symbol
    goes.
- **A path is named when git lists it** (accepted, not yet implemented). In a git repository a
  path a doc names exists when `git ls-files --cached --others --exclude-standard` lists it, or
  lists a file under it for a directory, or when the source walk holds it, never because a file
  is on one machine's disk; outside a git repository the disk answers. One listing serves
  `code-references` and claim evidence, and this replaces "or a file on disk outside `.git` and
  dependency directories" in the backticked-path rule above.

## Alternatives Considered

- **Index every name and report names that vanished.** Rejected: a match anywhere, a comment
  included, counts as existing.
- **An extractor per language.** Rejected: support would follow whichever stacks get one.
- **Every unbound name a finding.** Rejected: most docs name code without anchors; the lines a
  change touched tie the signal to its writer.
- **Anchors to definitions inside a function.** Rejected for now: such a name is not
  addressable from outside its enclosing body.
- **Offer mentions beside a definition.** Rejected: a mention is the wrong place to bind.
- **Flag a span as certain, or keep a check's own markers.** Rejected: an example names files
  never meant to exist, and two grammars for one syntax drift.
- **Demote `unlinked-reference` to a hint.** Rejected: it is provably an unwritten link.
- **Judge decision records and RFCs too.** Rejected: they name files that no longer exist or do
  not yet.
- **`ast.dump` for the pin.** Rejected: its output differs between versions by design; 3.13
  hides empty lists that 3.12 prints.
- **One Python for everyone, or the version recorded in the pin.** Rejected: an adopter's
  developers and CI legs choose their own interpreters, and a pin that is valid on one only
  moves the false drift elsewhere.
- **Hash the source text.** Rejected: a reformat would re-ask every claim.
- **Re-pin more often instead of naming a part:** the noise stays, and re-pinning without
  reading is the failure.
- **Line ranges as parts:** they move with every edit above them.
- **Finders for Python and Markdown only:** every config and template claim would stay
  whole-file.
- **tree-sitter now:** a heavy required dependency before more than one language needs a
  finder; it is the recorded route once several do, and markers serve until then.

## Consequences

- A renamed symbol in any language fails `claim-anchor` wherever a doc bound it, and a renamed
  file named in a code span is reported.
- The text-block hash is coarse: an edit inside the block re-asks the claim even when behaviour
  did not change.
- Binding is incremental, and a name defined only inside a function stays unbound with the
  suggestion saying why.
- A span is accepted while any file ends with it, so a renamed file whose old name another file
  still ends with is not reported. A quoted value is read without its quotes, and a name
  followed by `#anchor` or `:line` is not judged.
- The same code pins the same on every interpreter measured: 3.12.3, 3.12.10, 3.12.11 and
  3.13.5 agree on this repository's 85 pins and on 5,169 files of the standard library, its
  test suite and the installed packages, where `ast.unparse` disagreed on 255. A golden hash
  in `tests/test_checks_claim_anchor.py` holds every CI leg to one value.
- **Pins written by 0.3.x read as drifted once.** After upgrading, every Python anchor reports
  `claim-anchor/pinned-drift` and every claim pin on a Python file falls back to the
  commit-time comparison. `irminsul anchors --re-pin --all` after the upgrade is a format
  migration, not a re-read: it is the one case where a whole-tree re-pin is right.
- A Python release that parses unchanged code to a different tree still moves its hash; the
  empty-field rule absorbs only a new field left unset. Python 3.14 is not measured.
- A claim narrowed to a part is re-asked only when that part changes; a bare path still pins
  the whole file, so narrowing is a choice made per claim.
- A part that leaves out code its claim rests on under-asks it silently, which is why bare
  paths stay the default and each narrowing is re-read.
- An adopter's non-Python symbol anchor that relied on the guess stops resolving until the
  symbol is marked.

## Changes

- 2026-10-28: A Python pin hashes a canonical text of the syntax tree, not its `ast.unparse`.
- 2026-10-28: Accepted [Claim evidence names a part](../rfcs/claim-evidence-names-a-part.md):
  claim evidence and anchors name a part of a file through one set of finders.
- 2026-10-29: Accepted [A path is named when git lists it](../rfcs/a-path-is-named-when-git-lists-it.md).
