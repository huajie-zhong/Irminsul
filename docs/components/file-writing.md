---
id: file-writing
title: "File writing"
status: stable
summary: Writing files whole or not at all, in their own line endings, from templates in one strict environment.
describes:
  - "src/irminsul/atomic.py"
  - "src/irminsul/templating.py"
owns_tests:
  - "tests/test_atomic.py"
  - "tests/test_templating.py"
---

# File writing

The files Irminsul rewrites in place — a doc that `fix` repairs or `seed` fills, the baseline, the adoption record — go through `write_atomic`, and `init`, `seed` and `new` render their templates in the one strict environment `templating.environment` builds. What each guarantees is in its docstring, and `yaml_scalar` and `toml_string` say why neither writes a value with `tojson`.

Atomicity matters most where the file cannot be rebuilt: `irminsul adoption init` refuses to overwrite the [adoption record](adoption-record.md), so a half-written one would leave nothing it could recreate from. The [baseline](baseline.md) and the adoption record pin LF; [`fix`](new-list-regen.md) and [`seed`](seed.md) keep the endings a file had.

## Scope & Limitations

Not every writer goes through here: [`init`](init.md) writes its scaffold files and `new` its doc with LF on every platform on purpose, and the `external-links` cache is regenerable. `write_atomic` makes the replacement whole, not durable: it does not flush to disk, so a crash right after the rename can still lose it, and it takes no lock, so two runs writing one file each leave a whole file and the last one wins.
