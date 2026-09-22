---
id: render
title: Render
status: stable
describes:
  - render/render.go
owns_tests:
  - render/helper.go
  - render/*_test.go
  - render/missing_test.go
---

# Render

Three entries that ownership refuses: an ordinary source file, a glob, and a path that is
not there. `render/render_test.go` is left unowned on purpose, and stays unreported
because nothing in `render/` is owned yet.
