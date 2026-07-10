---
id: 0025-retire-render-subsystem
title: Retire the render and reference-stub subsystem
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
affects: [cli, new-list-regen]
resolved_by: docs/50-decisions/0013-retire-render-subsystem.md
required_updates: []
---

# RFC 0025: Retire the render and reference-stub subsystem

## Summary

Remove `irminsul render` (the MkDocs Material site builder), `irminsul regen
python`, `irminsul regen typescript`, the `src/irminsul/render/` package, the
`[mkdocs]` optional extra, and the CI render step. Irminsul keeps only the
check-and-derive core plus the agent manifest: the markdown tree is the artifact,
queried on demand and published by whatever tool a consumer already uses.

## Motivation

Two of irminsul's own principles point here:

- **Agent-first.** The primary readers are LLM agents, and they read `docs/**.md`
  and the code directly (via `AGENTS.md`, `irminsul context`, `irminsul surface`).
  None of them open a rendered HTML site. GitHub and IDEs already render markdown
  for humans-in-the-repo.
- **Hosting docs is a non-goal.** The principles state plainly that irminsul is a
  checker, not a hosting platform. The renderer was always a convenience at the edge
  of scope, serving an audience the tool says it does not serve: humans browsing a
  published website.

The render layer is a maintenance liability for that edge: it pulls heavy optional
dependencies (`mkdocs`, `mkdocs-material`, `mkdocstrings`), owns config and a CI
step, and recently produced a YAML-fold bug. The "derive, don't materialize" work
(RFC-0020) already removed the committed surface caches; this finishes the job by
removing the *render* half that the surfaces used to feed.

### The cascade

`regen python` / `regen typescript` exist only to emit mkdocstrings/TypeDoc **stub
pointers** (`::: module`) whose sole consumer is the renderer — mkdocstrings imports
each module at build time and renders its API. With no renderer the stubs point at
nothing, so they go too, along with `docs/40-reference/python|typescript/`, the
`[regen.typescript]` config, and the deferred "render-time surface projection"
roadmap item. (Notably, mkdocstrings *imports* target modules at build — the only
place irminsul's flow executed code; the static check core never does.)

## Detailed Design (what is removed)

- **Commands:** `irminsul render`, `irminsul regen python`, `irminsul regen
  typescript`, `irminsul regen all`.
- **Code:** `src/irminsul/render/` (the renderer Protocol + `MkDocsRenderer`),
  `src/irminsul/regen/python.py`, `src/irminsul/regen/typescript.py`.
- **Config:** the `[render]` and `[regen]` sections (`Render`, `Regen`,
  `RegenTypescript`).
- **Packaging:** the `[mkdocs]` optional extra and the related dependencies.
- **CI:** the `irminsul render (self)` dogfood step.
- **Docs:** the `render` component doc and the generated `40-reference/python`
  reference stubs; inbound references are repointed.

## Explicitly retained

- **`irminsul regen agents-md`** stays. `AGENTS.md` is the *agent* entrypoint, not a
  human site; it is a cache of the doc graph and is tracked as its own follow-up in
  ADR-0011, independent of the render subsystem.
- **`irminsul surface <kind>`** is the on-demand answer for code-derived surfaces.
- The `docs/40-reference/` layer remains for hand-written reference; it simply no
  longer holds auto-generated content.
- Language profiles (`languages/`) stay — they drive schema-leak and source-root
  detection, not rendering.

## Resolution

Accepted and implemented; resolved by
[`ADR-0013`](../../50-decisions/0013-retire-render-subsystem.md). Publishing a human
docs site is now explicitly out of scope: the markdown tree is portable to any
static-site generator a consumer chooses, and irminsul stays a checker plus an
on-demand deriver.
