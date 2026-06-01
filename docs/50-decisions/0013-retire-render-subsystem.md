---
id: 0013-retire-render-subsystem
title: "ADR-0013: Retire the render and reference-stub subsystem"
audience: adr
tier: 2
status: stable
describes: []
summary: Remove the MkDocs renderer and the regen python/typescript stubs; keep check + derive + agent manifest.
---

# ADR-0013: Retire the render and reference-stub subsystem

## Status

Accepted, 2026-05-31. Resolves [`0025-retire-render-subsystem`](../80-evolution/rfcs/0025-retire-render-subsystem.md). The "keep the `40-reference` layer for hand-written reference" clause below is superseded by [`ADR-0014`](0014-retire-tier-1-and-reference-layer.md).

## Context

Irminsul is agent-first, and agents read the markdown tree and the code directly;
they never open a rendered HTML site. The principles already name hosting docs a
non-goal. The MkDocs renderer and the `regen python`/`typescript` stubs that feed it
served only the human-website use case, while carrying heavy optional dependencies,
config, a CI step, and a recent rendering bug.

## Decision

Remove the render subsystem in full: the `render` command and `src/irminsul/render/`
package, `regen python`/`regen typescript` and their modules, the `[render]` and
`[regen]` config, the `[mkdocs]` extra, the CI render step, and the generated
`40-reference` reference stubs. Keep `regen agents-md` (the agent manifest, a
separate concern), `irminsul surface` (on-demand derivation), the `40-reference`
layer for hand-written reference, and the language profiles.

## Alternatives Considered

- **Keep render as an opt-in convenience.** Rejected: it is principle-clean as a
  transient build, but it serves a stated non-goal and is a standing maintenance
  surface; consumers can point any SSG at the portable markdown.
- **Keep `regen python` stubs, drop only the renderer.** Rejected: the stubs are
  inert without mkdocstrings to expand them, so they have no remaining consumer.
- **Also retire `regen agents-md`.** Rejected here: the manifest serves agents, not
  a human site; its retirement is a distinct follow-up (ADR-0011).

## Consequences

- Irminsul is a checker plus an on-demand deriver; the markdown tree is the artifact.
- Publishing a browsable site is out of scope; teams use their own SSG on the
  markdown.
- mkdocstrings was the only build step that imported target code; the tool's flow is
  now uniformly static.
