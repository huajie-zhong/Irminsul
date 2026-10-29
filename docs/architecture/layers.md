---
id: layers
title: Layers
status: stable
summary: The six layers and the rules each sets.
describes: []
---

# Layers

A docs tree has six layers, each a folder under `docs_root`. A layer answers one kind of question, and the checks and commands that care about a kind of doc find it through its layer.

| Layer | Answers | Irminsul reads it for |
|-------|---------|-----------------------|
| `foundation` | Why the project exists, what it values, what it will not do | `foundation-readiness`, `seed`, protected claims |
| `architecture` | How the parts fit and how data flows between them | `seed`, protected claims |
| `components` | What one component does; each doc claims source with `describes` | source ownership, required tests, schema leaks, `new component` |
| `decisions` | Why a choice was made (ADRs) | live-doc scoping, `new adr` |
| `rfcs` | What is proposed and where it is in the change lifecycle | the whole [change lifecycle](../components/change.md) |
| `guides` | How to do something: how-tos, operations, and docs about the doc system | nothing beyond the checks every doc gets |

Doc ids are global bare slugs: the folder does not namespace them, so two docs with the same filename in different layers collide. A folder's INDEX takes the folder's name as its id.

## Rules per layer

Two rules are set per layer rather than per doc, so every doc in a layer is held to the same standard:

- `require_tests` — a doc that claims source with `describes` lists the tests that verify it (`coverage`). <!-- anchor: src/irminsul/config.py#Layer.require_tests @sha256:2a17b30bc300 -->
- `require_scope_section` — a doc carries a `## Scope & Limitations` section (`boundary`). <!-- anchor: src/irminsul/config.py#Layer.require_scope_section @sha256:dc877096893f -->

A folder's INDEX is navigation and follows no layer rules.

## Configuration

Folder names and rules live under `[layers]` in `irminsul.toml`; the [config reference](../components/config.md#layers) lists the keys.

## Scope & Limitations

Irminsul does not require every layer to exist or to have content; an INDEX with no docs beside it or in any folder beneath it is a `phantom-layer` error only when that INDEX claims to be finished. It does not decide which layer a doc belongs in — that is an authoring judgment.
