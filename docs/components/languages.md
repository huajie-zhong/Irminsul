---
id: languages
title: Language profiles
status: stable
describes:
  - src/irminsul/languages/**
owns_tests:
  - tests/test_languages.py
  - tests/test_languages_go_rust.py
---

# Language profiles

A `LanguageProfile` is a pure-data record:

- `name` — the registry key (`"python"`, `"typescript"`, `"go"`, or `"rust"`)
- `source_root_candidates` — directories the [init detector](init.md) checks when scaffolding a new codebase
- `schema_leak_patterns` — compiled regex patterns the [schema-leak check](checks.md) applies line-by-line to docs under the protected glob

Patterns are anchored at start-of-line (with leading whitespace allowed) so casual prose mentions don't trigger findings — only lines that look like definitions match.

Python, TypeScript, Go, and Rust profiles are included. Adding another language requires creating a profile, with its schema-leak patterns and code-fence labels, and registering it in `LANGUAGE_REGISTRY`; config validation and `schema-leak` read the registry, so no check changes. Auto-detection in `irminsul init` is separate code, so a new language is used through `--language` until the detector learns its marker files.

## Scope & Limitations

Language profiles are pure-data records — they contain no behavioral logic. Adding a language by creating a new profile does not change any check behavior; checks that use profiles (schema-leak, init detector) consume them generically. Profiles do not validate that source files conform to the expected language syntax.
