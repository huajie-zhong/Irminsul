---
id: layers
title: Layers
status: stable
describes: []
---

# Layers

A docs tree has six layers, each a folder under `docs_root`. A layer answers one kind of question, and the checks and commands that care about a kind of doc find it through its layer.

| Layer | Answers | Irminsul reads it for |
|-------|---------|-----------------------|
| `foundation` | Why the project exists, what it values, what it will not do | `foundation-readiness`, `seed`, protected claims |
| `architecture` | How the parts fit and how data flows between them | `seed`, protected claims, change impact |
| `components` | What one component does; each doc claims source with `describes` | source ownership, required tests, schema leaks, `new component` |
| `decisions` | Why a choice was made (ADRs) | live-doc scoping, `new adr`, `seed` |
| `rfcs` | What is proposed and where it is in the change lifecycle | the whole [change lifecycle](../components/change.md) |
| `guides` | How to do something: how-tos, operations, and docs about the doc system | nothing beyond the checks every doc gets |

Doc ids are global bare slugs: the folder does not namespace them, so two docs with the same filename in different layers collide. A folder's INDEX takes the folder's name as its id.

## Rules per layer

Three rules are set per layer rather than per doc, so every doc in a layer is held to the same standard:

- `require_tests` — a doc that claims source with `describes` lists the tests that verify it (`coverage`).
- `require_scope_section` — a doc carries a `## Scope & Limitations` section (`boundary`).
- `forbid_speculation` — a doc describes what is true now, without roadmap vocabulary (`reality`).

The components layer turns all three on; the others turn none on. A folder's INDEX is navigation and follows no layer rules.

## Configuration

Folder names and rules live under `[layers]` in `irminsul.toml`; the [config reference](../components/config.md#layers) lists the keys. Folders under `docs_root` that are not a layer are allowed and follow only the checks every doc gets.

## This repository

```
docs/
├── foundation/     principles, anti-patterns, enforcement model
├── architecture/   overview, check pipeline, component hierarchy, levels and views, layers, tooling
├── components/     one doc per component of src/irminsul/
├── decisions/      ADRs
├── rfcs/           proposals in flight
└── guides/         bootstrap, release, private docs, agent protocol, style guide
```

## Scope & Limitations

Irminsul does not require every layer to exist or to have content; an INDEX with no docs beside it is a `phantom-layer` error only when that INDEX claims to be finished. It does not decide which layer a doc belongs in — that is an authoring judgment.
