---
id: languages
title: Language profiles
status: stable
summary: Language-profile registry.
describes:
  - src/irminsul/languages/**
owns_tests:
  - tests/test_languages.py
  - tests/test_languages_go_rust.py
---

# Language profiles

A `LanguageProfile` is a pure-data record, and `LANGUAGE_REGISTRY` is the only lookup: [config](config.md) validation, `schema-leak`, the [init detector](init.md), `code-references` and the file selection of the [surface](surface.md) extractors and packs all read it. Adding a language is a profile constant registered there and changes no check; `languages/base.py` says what each field is for. Python, TypeScript, Go and Rust are included. What an extractor reads inside the language's files stays the extractor's own code, written once per surface.

## Scope & Limitations

Language profiles are pure-data records with no behavioral logic; the checks that use them (`schema-leak`, the init detector) consume them generically. Profiles do not validate that source files conform to the expected language syntax.
