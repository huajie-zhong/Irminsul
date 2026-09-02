---
id: 0002-support-fresh-start-init
title: Support fresh-start init
audience: adr
tier: 2
status: draft
describes: []
---

# ADR 0002: Support fresh-start init

## Status

Proposed, 2026-05-09. Its topology clauses were superseded by
[`ADR-0022`](0022-reduce-supported-repository-topologies.md) and have been
removed from the text below; the fresh-start decision itself stands.

## Context

`irminsul init` currently assumes the common target is an existing codebase. In
non-interactive mode, an empty directory with no code signals exits with an
error. In interactive mode, the empty-directory path is framed as a docs-only
question, which makes fresh project creation possible only as an implicit
negative answer.

That does not match the foundation goal that adoption should be easy from the
first commit. The strongest version of Irminsul is a project where docs, checks,
and code grow together rather than a project that adopts the system after drift
has already accumulated.

## Decision

Support fresh-start setup as part of `irminsul init`, with topology as an
explicit part of the flow.

The public command is:

```bash
irminsul init --fresh
```

When `irminsul init` runs interactively in a directory with no code signals, it
should prompt for setup intent and include fresh-start as one of the choices.
There will not be an `irminsul new project` command for this feature because
`new` is already the command family for creating doc atoms inside an initialized
repo.

Non-interactive `--fresh` should create docs, config, CI wiring, and an empty
source root. It should not create language-specific starter code or tests because
Irminsul cannot safely assume the project's implementation language or framework.

Which repository layouts `init` scaffolds, and how a private docs tree reaches
a separate code repo, are decided by
[`ADR-0022`](0022-reduce-supported-repository-topologies.md), not here.

Fresh-start may run in a non-empty directory that has no code signals, such as a
repo containing only `README.md` and `.gitignore`.

The generated first project ADR should record both adoption of Irminsul and the
choice to start the project under Irminsul from day one.

## Alternatives Considered

- **Keep empty directories as an error:** avoids a new init branch, but makes the
  best adoption moment feel unsupported.
- **Add `irminsul new project`:** separates project creation from adoption, but
  conflicts with the existing CLI style where `new` scaffolds doc atoms.
- **Generate starter code and tests:** convenient for Python projects, but wrong
  for projects that are not Python or that already have a preferred generator.
- **Make empty non-interactive init fresh by default:** convenient, but it could
  hide wrong-path mistakes in automation.

## Consequences

Fresh project adoption becomes intentional and documented. Users can start with a
valid docs gate before code exists, and CI can enforce structure from the first
PR.

The init flow gains another branch and needs tests for no-code directories,
non-empty no-code directories, and no-overwrite behavior. Implementation must
carefully distinguish missing future source roots from accidental missing source
roots in an already-adopted repo.
