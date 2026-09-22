---
id: anchors-bind-code-names-in-any-language
title: "Anchors bind code names in any language"
status: stable
describes: []
summary: A doc binds each code name it cites to the file that defines it with an anchor; Irminsul lists unbound names for review, suggests candidate files, and resolves anchors in any language.
---

# Anchors bind code names in any language

## Status

Accepted, 2026-09-15.

## Context

A doc that names `fetchUserSession()` goes stale when the function is renamed, and a
tool that cannot tell which function the doc meant cannot report it. Framework
extractors resolve commands, options, and routes for the frameworks they know; the
symbol index reads Python only; and an index of every name in a repository matches
names left in comments and flags other tools' names.

An anchor already records the binding precisely: `<!-- anchor: path#symbol -->` names the
file and symbol a paragraph describes, and `claim-anchor` reports a missing symbol as
certain. It resolved symbols by parsing Python, so an anchor into any other language was
unreadable.

Deciding which file a name refers to is judgment a person or agent makes once; checking
that the file still defines it is mechanical, forever.

## Decision

- **Anchors resolve in any language.** A Python file resolves a symbol through its syntax
  tree, as before. Any other text file resolves a symbol when the name appears in it as a
  whole token, and pins the hash of the indented block that starts at the name's first
  occurrence, with whitespace normalized. A file anchor without a symbol pins the file's
  normalized text.
- **Unbound names are listed for review.** Under `irminsul list review --changed` or
  `--base`, a sentence on a changed line that names code — a call such as `name()`, a
  dotted or snake_case or camelCase identifier — that no surface or path resolves and no
  anchor in the doc binds is listed with those names as `unbound`. The queue asks; it does
  not fail a run.
- **Suggestions are mechanical, the choice is not.** `irminsul anchors --suggest` lists
  each unbound name with the source files that contain it, definition-like lines first,
  and the marker to paste. The agent chooses the file and writes the anchor.
- **Framework extractors stay** as precision for the kinds they know, such as options
  checked against their command.

## Alternatives Considered

- **Index every name in the repository and report names that vanished.** Rejected: a
  match anywhere, such as a comment, counts as existing, and names that belong to other
  tools would be reported without end.
- **Write an extractor per language or framework.** Rejected: support would follow
  whichever stacks get an adaptor, and a codebase of another shape gets nothing.
- **Report every unbound name as a finding.** Rejected: most existing docs name code
  without anchors, so the signal would drown; reviewing the lines a change touched keeps
  it tied to the person writing them.

## Consequences

- A renamed symbol in any language fails `claim-anchor` wherever a doc bound it.
- The text-block hash is coarser than a syntax tree: an edit inside the block re-pins the
  claim for review even when it does not change behavior.
- Binding is incremental; docs gain anchors as agents touch them.
