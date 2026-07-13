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
---

# Config

`irminsul.toml` lives at the root of every codebase that adopts Irminsul. It is a Pydantic-validated TOML file declaring where docs and source live, which checks are active, and which language profiles to apply.

The schema enforces structural invariants (unknown check names are rejected; the enabled languages are an enum) but stays out of the way for everything else. Defaults exist for every section so a minimal toml works, while the scaffold writes the useful knobs explicitly so projects can discover them without reading source.

A new check registers in two places or the schema rejects it as unknown: the registry in `src/irminsul/checks/__init__.py` and the corresponding known-name tuple here (`HARD_CHECKS`, `SOFT_DETERMINISTIC_CHECKS`, or `SOFT_LLM_CHECKS`) — plus the consuming repo's `irminsul.toml` list to actually enable it.

Hard checks and deterministic soft checks are enabled by default. Projects can override `checks.hard` or `checks.soft_deterministic` when they need a narrower profile. `external-links` is included in the soft deterministic list, but `[checks.external_links].enabled` remains `false` by default because it performs network I/O.

`checks.terminology_overload.rules` configures ambiguous terminology warnings. There are no default rules — which terms are overloaded is project-specific, so each project (including this repo, whose own config declares a `coverage` rule) defines its own.

Generated configs include the stable/useful deterministic sections: paths, hard and soft checks, implemented nested check settings, overrides, and languages. The schema is closed — unknown keys are rejected rather than ignored, so a stale or misspelled table fails fast instead of silently doing nothing.

A loader walks up from the invocation directory looking for `irminsul.toml` so subcommands work regardless of cwd.

## Scope & Limitations

Config declares where files live and which checks are active — it does not validate source file contents. `find_config()` walks upward from the invocation directory but does not scan sibling directories or auto-discover projects. Config does not enforce runtime behavior; it only shapes which checks run.
