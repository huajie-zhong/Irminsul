---
id: render
title: Renderer
audience: explanation
tier: 3
status: stable
depends_on:
  - docgraph
describes:
  - src/irminsul/render/**
tests:
  - tests/test_render_mkdocs.py
---

# Renderer

A small `Renderer` Protocol with one method: `build(graph, out_dir)`. The current implementation is `MkDocsRenderer`.

The MkDocs backend generates a `mkdocs.yml` from the [DocGraph](docgraph.md) — site name from config, theme = Material, nav grouped by layer prefix (00→90) — then shells out to `python -m mkdocs build`. Going through `python -m` (rather than the `mkdocs` binary on PATH) keeps the renderer working in unactivated venvs and pipx-installed environments.

MkDocs is an *optional* dependency (`pip install 'irminsul[mkdocs]'`). If it's not importable, the renderer raises a `MkDocsRenderError` with a clear install hint instead of crashing.

Adding a Docusaurus or Sphinx backend means writing a new class that satisfies the Protocol and exposing a config knob; no core changes.

## Scope & Limitations

The renderer builds a static site and does not host it — deployment is out of scope. It does not validate docs before rendering; run `irminsul check` first. Adding a new backend requires implementing the `Renderer` Protocol and exposing a config knob; no core changes are needed.
