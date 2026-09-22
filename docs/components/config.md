---
id: config
title: Config
status: stable
describes:
  - src/irminsul/config.py
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

`irminsul.toml` lives at the root of every codebase that adopts Irminsul. It is a Pydantic-validated TOML file declaring where docs and source live, which checks are active, and which language profiles to apply.

The schema enforces structural invariants (unknown check names are rejected; the enabled languages are an enum) but stays out of the way for everything else. Defaults exist for every section so a minimal toml works, while the scaffold writes the useful knobs explicitly so projects can discover them without reading source.

A new check registers in two places or the schema rejects it as unknown: the registry in `src/irminsul/checks/__init__.py` and the corresponding known-name tuple here (`DEFAULT_CHECKS`, or `OPT_IN_CHECKS` for a check that is off by default) — plus the consuming repo's `checks.enabled` to actually enable it. A config that still splits its checks into the two lists this key replaced fails to load with `checks.enabled` named.

Every check except the opt-in `agents-manifest` is enabled by default. Projects can list fewer in `checks.enabled`. `external-links` is in the default list, but `[checks.external_links].enabled` remains `false` by default because it performs network I/O.

`checks.terminology_overload.rules` configures ambiguous terminology warnings. There are no default rules — which terms are overloaded is project-specific, so each project (including this repo, whose own config declares a `coverage` rule) defines its own.

Generated configs include the stable/useful deterministic sections: paths, the enabled checks, implemented nested check settings, overrides, and languages. The schema is closed — unknown keys are rejected rather than ignored, so a stale or misspelled table fails fast instead of silently doing nothing.

A loader walks up from the invocation directory looking for `irminsul.toml` so subcommands work regardless of cwd.

## Keys

| Key | Default | Meaning |
|-----|---------|---------|
| `project_name` | `"untitled"` | Shown by `orient` and offered to `seed` |
| `paths.docs_root` | `"docs"` | Root of the doc tree the graph walks, relative to the repository; `..` and a drive-absolute path are rejected |
| `paths.source_roots` | `["src", "app", "lib"]` | Source inventory boundaries (see below) |
| `paths.baseline` | `".irminsul-baseline.json"` | Where `check --init-baseline` writes the [baseline](baseline.md) |
| `paths.adoption` | `".irminsul-adoption.json"` | Where `check --init-adoption` writes the [adoption record](adoption-record.md) |
| `paths.extra_docs` | `["README.md", "AGENTS.md", "CLAUDE.md"]` | Guidance files outside the doc graph, relative to the repository root; the checks that read guidance, ignore comments, and `list review` read them, and a siblings layout can name the code repository's files through `../` | <!-- irminsul:ignore prose-file-reference reason="default value" -->
| `paths.sources` | `[]` | Git repositories other than this one that the roots above reach into, each an array-of-tables entry with a `name`, a `path`, and a `ref`. Declaring one is what lets the [adoption record](adoption-record.md) name a file from that repository; reading those roots needs no declaration. See below |
| `checks.enabled` | every check except the opt-in manifest check | Checks to run |

`paths.baseline` and `paths.adoption` are validated as committable in-repository file paths: not empty, not absolute, no `..`, not a directory. Both files *are* seals, and both are judged by comparing them with their content at the merge base — so one written outside the repository cannot be committed, cannot be watched by the generated workflow, and reads as absent at the base on every run. For the adoption record that means every run is a first adoption and the only-shrinks ratchet is gone, and it failed that way in silence: a file appeared where it was told to, and the gate stayed green.
| `checks.schema_leak.protected_paths` | every doc in the components layer | Docs `schema-leak` scans |
| `checks.external_links.enabled` | `false` | Whether `external-links` makes network requests at all |
| `checks.external_links.timeout_seconds` | `5.0` | Per-request timeout |
| `checks.external_links.cache_path` | `".irminsul-cache/external-links.json"` | Result cache, kept between runs |
| `checks.external_links.ttl_hours` | `168` | How long a successful result stays cached |
| `checks.stale_reaper.deprecated_threshold_days` | `180` | Age at which a deprecated doc is reported |
| `checks.rfc_follow_through.accepted_threshold_days` | `90` | Days since an accepted RFC's last commit after which it is reported when no doc it names in `affects` or `required_updates` was committed since |
| `checks.glossary_discipline.glossary_path` | `"docs/GLOSSARY.md"` | The canonical [glossary](../GLOSSARY.md) | <!-- irminsul:ignore prose-file-reference reason="default value" -->
| `checks.parent_child.length_warning_lines` | `300` | INDEX body length that triggers a warning |
| `checks.terminology_overload.rules` | `[]` | Each rule has a `term`, its `explicit_phrases`, and a `suggestion` |
| `checks.inventory_drift.generic` | `[]` | Config-declared surface kinds: each has a `kind`, a file `glob`, a `pattern`, an `identity` template (default `{1}`), and optional `mention_pattern` and `prose_named` capabilities |
| `overrides.mtime_drift_days` | `30` | How far a doc may trail its described source before `mtime-drift` warns |
| `languages.enabled` | `["python"]` | Language profiles to apply |
| `frameworks.enabled` | every pack | Framework packs whose surfaces are extracted |
| `frameworks.command_names` | from package manifests | Program names docs use to invoke commands |
| `layers.<layer>.path` | see below | The layer's folder under `docs_root` |
| `layers.<layer>.require_tests`, `require_scope_section`, `forbid_speculation` | on for components, off elsewhere | Rules every doc in the layer follows |

## Layers

Irminsul gives meaning to six layers: `foundation`, `architecture`, `components`, `decisions`, `rfcs`, and `guides`. Each is a folder under `docs_root`, and every check, command, and scaffold finds a layer through `[layers]` rather than a fixed folder name, so a project can rename one:

```toml
[layers.components]
path = "modules"
```

A `[layers.<layer>]` table overrides only the keys it sets, so the renamed layer above keeps the components rules. Two layers cannot share a folder. Other folders under `docs_root` are allowed and carry no layer rules.

## Source discovery policy

`paths.source_roots` defines the explicit inventory boundaries. `source_includes` is an optional Git-wildmatch allow-list; an empty list includes every otherwise eligible file. `source_excludes` is a veto list and wins over includes. `honor_gitignore` defaults to `true` and applies repository-local `.gitignore` files with nested negation and last-match semantics. Global Git excludes and `.git/info/exclude` are not read, so inventory is reproducible across machines. `test_patterns` names the test implementation files inside that boundary, replacing the enabled languages' own conventions where no convention describes the layout; it is the only thing that decides which files `test-ownership` governs, and excluding tests from the walk instead would hide them from every other check too. `test_roots` adds directories that hold tests but are not source roots, such as a top-level `tests/`, and declaring one closes the ownership rule over it: every test file under a declared root needs an owner, where an undeclared tree is adopted one directory at a time. It widens no other check — a tree the rest should read belongs in `source_roots`.

Patterns match the normalized POSIX display path used by `describes:`. Same-repository files use repository-relative paths; files from an external source root use paths relative to that source root. Built-in cache/dot-path exclusions, `.gitignore`, and explicit excludes cannot be reversed by an include.

Every configured root is deliberate, so a `.gitignore` above it cannot silently undo the configuration: an ignore rule that would hide the root directory itself is dropped, and the root is inventoried anyway. The live case is generated code — a tree that is gitignored because it is build output but is still a source root because docs have to own it. Ignore rules that select files *inside* the root are ordinary excludes and still apply; the root is un-hidden, not un-filtered. The nearest enclosing repository is the ignore boundary.

`rfc-lifecycle` is enabled by default: it is inert in repositories without RFCs
and checks their states and links when they exist; `diff-integrity`, under `--diff`,
protects implemented RFC history.

## Declared sources

```toml
[paths]
source_roots = ["../code/src", "../code/tests"]

[[paths.sources]]
name = "engine"
path = "../code"
ref = "origin/main"
```

Three fields, and each is refused rather than repaired when it cannot mean one thing:

- **`name`** is what the adoption record stores, so it is a bare identifier with no slashes.
  It is the binding: an entry says which source it came from, not which root the walk
  happened to resolve it through, so editing `source_roots` can no longer re-point an
  existing exception at another repository's history.
- **`path`** is that repository's own root, relative to this one — the repository, not a
  directory inside it, so every configured root under it resolves to one source. Two
  declared paths may not overlap or repeat, and neither may two names: a root under both
  would have no single source, and guessing one is how an exception gets verified against
  the wrong history. Changing a path is a configuration change the diff gate reports.
- **`ref`** is the history a pinned revision has to be part of. Fully qualified
  (`refs/heads/main`) or remote-qualified (`origin/main`). A bare `main` is refused: in a
  checkout that is the *local* branch, movable by anyone and invisible when it moves, and
  the boundary has to be a statement about the repository's shared history. Exactly one
  candidate is tried — the value itself when it starts with `refs/`, otherwise
  `refs/remotes/<value>` — so there is no precedence order to get wrong.

Naming a ref is not a claim that it is protected. Irminsul checks that a pin is contained in
that ref's history; whether the branch is protected, and whether anyone reviewed what reached
it, are repository settings and human reviews outside this tool — see
[private docs](../guides/private-docs.md) for the two columns.

Declaring a source is what *adopting* from a repository requires. A `siblings` layout that
records no cross-repository debt needs none, and every other check reads those roots as
before.

## Scope & Limitations

Config declares where files live and which checks are active — it does not validate source file contents. `find_config()` walks upward from the invocation directory but does not scan sibling directories or auto-discover projects; a command whose `--path` sits below the directory holding `irminsul.toml` exits 2 and names that directory, because the doc tree it would read is the wrong one. Explicit source roots may resolve outside the config repository; discovered symlink entries are still contained to the root that selected them.
