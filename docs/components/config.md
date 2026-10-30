---
id: config
title: Config
status: stable
summary: "`irminsul.toml` schema."
describes:
  - src/irminsul/config.py
depends_on:
  - checks
  - surface
  - user-errors
owns_tests:
  - tests/test_config.py
  - tests/test_extra_docs.py
  - tests/test_layer_rules.py
inventory:
  - kind: config-keys
    source: src/irminsul/config.py
    explained_in: self
    omit:
      - parts
---

# Config

`irminsul.toml` lives at the root of every codebase that adopts Irminsul: a Pydantic-validated TOML declaring where docs and source live, which checks run and which language profiles apply. Every section has defaults, so a minimal file works. The schema is closed, so an unknown key is rejected rather than ignored and a stale or misspelled table fails fast instead of silently doing nothing.

A new check registers once, in `REGISTRY` in `src/irminsul/checks/__init__.py`, and the schema knows it from there; it is enabled by default unless its class declares the `opt_in` flag. Framework pack names come from the pack registry the same way.
<!-- anchor: src/irminsul/checks/base.py#CheckFlag.opt_in @sha256:905c9f146ced -->

`diff-integrity` reads the config at the merge base through `parse_snapshot`, which keeps the check, pack and language names this version no longer registers, so a change that deletes a check's code is still seen removing it from `checks.enabled`.

## Keys

| Key | Meaning |
|-----|---------|
| `project_name` | Shown by `orient` and offered to `seed` |
| `paths.docs_root` | Root of the doc tree the graph walks; it must stay inside the repository |
| `paths.source_roots` | Source inventory boundaries, which may sit outside the repository |
| `paths.source_includes`, `paths.source_excludes`, `paths.honor_gitignore` | Which files under the roots count as source |
| `paths.test_patterns` | Which files are tests, replacing the languages' conventions; it alone decides what `test-ownership` governs, since excluding tests from the walk would hide them from every other check too |
| `paths.test_roots` | Test directories outside the source roots; declaring one closes the ownership rule over it, where an undeclared tree is adopted one directory at a time |
| `paths.baseline`, `paths.adoption` | Where `irminsul baseline init` and `irminsul adoption init` write the [baseline](baseline.md) and the [adoption record](adoption-record.md) |
| `paths.extra_docs` | Guidance files outside the doc graph that `list review`, ignore comments and the checks that read guidance also read |
| `paths.sources` | Other git repositories the roots reach into; declaring one is what lets the adoption record name a file from it |
| `checks.enabled` | Checks to run |
| `checks.schema_leak.protected_paths` | Docs `schema-leak` scans |
| `checks.external_links.enabled` | Whether `external-links` makes network requests; it is in `checks.enabled` but does nothing until this is true |
| `checks.external_links.timeout_seconds`, `checks.external_links.cache_path`, `checks.external_links.ttl_hours` | Per-request timeout, result cache kept between runs, and how long a success stays cached |
| `checks.stale_reaper.deprecated_threshold_days` | Age at which a deprecated doc is reported |
| `checks.rfc_follow_through.accepted_threshold_days` | Days an accepted RFC may sit with none of the docs it names committed after it |
| `checks.glossary_discipline.glossary_path` | The canonical [glossary](../GLOSSARY.md) |
| `checks.parent_child.length_warning_lines` | INDEX body length that triggers a warning |
| `overrides.mtime_drift_days` | How far a doc may trail its described source before `mtime-drift` warns |
| `languages.enabled` | Language profiles to apply |
| `frameworks.enabled`, `frameworks.command_names` | Framework packs whose surfaces are extracted, and the program names docs use to invoke commands |
| `surface.rules` | Config-declared surface kinds, each a `kind`, `globs`, `pattern`, `identity`, optional `guard` and optional `mention_pattern`, in the shape of a [framework pack](surface.md)'s rules |
| `layers.<layer>.path`, `require_tests`, `require_scope_section` | The layer's folder, and the rules every doc in it follows |

Under `--diff`, [`diff-integrity`](checks.md) compares every key with its value at the merge base ([A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md)). A trailer answers a finding about a key by naming its dotted name as the subject, with `irminsul.toml` as its path, spelled as this table spells it with the layer filled in, as in `layers.components.require_tests`, and a field of a list of tables by its name under the list, as in `paths.sources.ref`.

`paths.baseline` and `paths.adoption` must be committable in-repository file paths, because both files are seals judged against their content at the merge base: one written outside the repository reads as absent at the base on every run, and nothing else reports it.

## Layers

Irminsul gives meaning to six layers, `foundation`, `architecture`, `components`, `decisions`, `rfcs` and `guides`. Every check, command and scaffold finds a layer through `[layers]` rather than a fixed folder name, so a project can rename one, and the table overrides only the keys it sets:

```toml
[layers.components]
path = "modules"
```

Two layers cannot share a folder. Other folders under `docs_root` are allowed and carry no layer rules.

## Declared sources

```toml
[paths]
source_roots = ["../code/src", "../code/tests"]

[[paths.sources]]
name = "engine"
path = "../code"
ref = "origin/main"
```

Each field is refused rather than repaired when it cannot mean one thing, and `SourceSpec` says why for each. A `ref` names the history a pin must be part of, not a protection: whether the branch is protected and reviewed is a repository setting outside this tool ([private docs](../guides/private-docs.md) has the two columns).

## Scope & Limitations

Config declares where files live and which checks are active — it does not validate source file contents. `find_config()` walks upward from the invocation directory but does not scan sibling directories or auto-discover projects; a command whose `--path` sits below the directory holding `irminsul.toml` exits 2 and names that directory, because the doc tree it would read is the wrong one. Explicit source roots may resolve outside the config repository; discovered symlink entries are still contained to the root that selected them.
