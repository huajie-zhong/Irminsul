---
id: languages
title: Language profiles
audience: reference
tier: 3
status: stable
owner: "@hz642"
last_reviewed: 2026-05-08
describes:
  - src/irminsul/languages/**
tests:
  - tests/test_languages.py
  - tests/test_languages_go_rust.py
---

# Language profiles

A `LanguageProfile` is a pure-data record:

- `name` — the registry key (`"python"`, `"typescript"`)
- `source_root_candidates` — directories the [init detector](init.md) checks when scaffolding a new codebase
- `schema_leak_patterns` — compiled regex patterns the [schema-leak check](checks.md) applies line-by-line to docs under the protected glob

Patterns are anchored at start-of-line (with leading whitespace allowed) so casual prose mentions don't trigger findings — only lines that look like definitions match.

v0.1.0 ships `python` and `typescript` profiles. Adding Go or Rust requires creating a profile and registering it in `LANGUAGE_REGISTRY` — no core changes.
