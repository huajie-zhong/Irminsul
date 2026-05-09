---
id: config
title: Config
audience: reference
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes:
  - src/irminsul/config.py
tests:
  - tests/test_config.py
---

# Config

`irminsul.toml` lives at the root of every codebase that adopts Irminsul. It's a small Pydantic-validated TOML file declaring where docs and source live, which checks are active, and which language profiles to apply.

The schema enforces structural invariants (unknown check names are rejected; render targets are an enum) but stays out of the way for everything else. Defaults exist for every section so a minimal toml works.

A loader walks up from the invocation directory looking for `irminsul.toml` so subcommands work regardless of cwd.
