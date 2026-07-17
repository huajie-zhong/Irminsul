---
id: config
title: Config
audience: reference
tier: 3
status: stable
describes:
  - src/irminsul/config.py
tests:
  - tests/test_config.py
implements:
  - 0035-rfc-lifecycle-integrity-and-frozen-records
---

# Config

`irminsul.toml` lives at the root of every codebase that adopts Irminsul. It is a Pydantic-validated TOML file declaring where docs and source live, which checks are active, and which language profiles to apply.

The schema enforces structural invariants (unknown check names are rejected; the enabled languages are an enum) but stays out of the way for everything else. Defaults exist for every section so a minimal toml works, while the scaffold writes the useful knobs explicitly so projects can discover them without reading source.

A new check registers in two places or the schema rejects it as unknown: the registry in `src/irminsul/checks/__init__.py` and the corresponding known-name tuple here (`HARD_CHECKS` or `SOFT_DETERMINISTIC_CHECKS`) — plus the consuming repo's `irminsul.toml` list to actually enable it.

Hard checks and deterministic soft checks are enabled by default. Projects can override `checks.hard` or `checks.soft_deterministic` when they need a narrower profile. `external-links` is included in the soft deterministic list, but `[checks.external_links].enabled` remains `false` by default because it performs network I/O.

`checks.terminology_overload.rules` configures ambiguous terminology warnings. There are no default rules — which terms are overloaded is project-specific, so each project (including this repo, whose own config declares a `coverage` rule) defines its own.

Generated configs include the stable/useful deterministic sections: paths, hard and soft checks, implemented nested check settings, overrides, and languages. The schema is closed — unknown keys are rejected rather than ignored, so a stale or misspelled table fails fast instead of silently doing nothing.

A loader walks up from the invocation directory looking for `irminsul.toml` so subcommands work regardless of cwd.

## Source discovery policy

`paths.source_roots` defines the explicit inventory boundaries. `source_includes` is an optional Git-wildmatch allow-list; an empty list includes every otherwise eligible file. `source_excludes` is a veto list and wins over includes. `honor_gitignore` defaults to `true` and applies repository-local `.gitignore` files with nested negation and last-match semantics. Global Git excludes and `.git/info/exclude` are not read, so inventory is reproducible across machines.

Patterns match the normalized POSIX display path used by `describes:`. Same-repository files use repository-relative paths; files from an external source root use paths relative to that source root. Built-in cache/dot-path exclusions, `.gitignore`, and explicit excludes cannot be reversed by an include.

Every configured root is deliberate. An enclosing repository rule that ignores the root directory does not hide it, which preserves private-docs layouts with a gitignored nested code checkout. More specific ignore rules for files inside the root still apply, using the nearest enclosing repository as the ignore boundary.

`rfc-lifecycle-integrity` is a default hard check: it is inert in repositories
without RFC lifecycle atoms and protects implemented RFC history when they exist.

## Scope & Limitations

Config declares where files live and which checks are active — it does not validate source file contents. `find_config()` walks upward from the invocation directory but does not scan sibling directories or auto-discover projects. Explicit source roots may resolve outside the config repository; discovered symlink entries are still contained to the root that selected them.
