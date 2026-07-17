---
id: 0036-source-discovery-policy
title: "Source discovery policy"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
affects:
  - change
  - checks
  - config
  - init
  - status
  - surface
---

# RFC 0036: Source discovery policy

## Summary

Make source inventory a single deterministic policy shared by checks, reports,
derived surfaces, and change analysis. The policy honors repository-local
`.gitignore` files, adds explicit include and exclude patterns, and rejects
symlinked entries that escape an explicitly configured source root.

Configured source roots may still live outside the docs repository or themselves
be symlinks. The containment boundary is each resolved configured root, not the
docs repository.

## Motivation

The current walker recursively treats almost every file below a source root as
source. It ignores only dot-directories, Python bytecode caches, and bytecode
files. Generated output, vendored trees, build artifacts, binary assets, and
dependencies therefore enter ownership totals and every consumer that reuses the
walker even when Git ignores them.

File symlinks are followed by `Path.is_file()` without verifying the resolved
target. A lexical path below a configured source root can therefore make checks
read a file outside that root. Deleted-file change analysis has a second,
path-only implementation of the inventory rule, so adding filters only to the
disk walk would make before/after behavior disagree.

## Requirements

### Requirement: Apply one deterministic source policy
ID: deterministic-source-policy
Provenance: code

All source-inventory consumers MUST apply the same built-in exclusions,
repository-local ignore rules, and explicit include/exclude patterns.

#### Scenario: Git ignores generated output
- **WHEN** a repository-local `.gitignore` excludes a file below a configured source root
- **THEN** the file is absent from ownership checks, reports, and derived surfaces

#### Scenario: Explicit patterns overlap
- **WHEN** a file matches both an include and an exclude pattern
- **THEN** the exclude wins and the file is absent from source inventory

### Requirement: Keep configured roots explicit
ID: configured-root-boundary
Provenance: code

An explicitly configured source root MUST remain eligible even when an enclosing
repository ignores the root directory, while ignore rules that target files
inside that root MUST still apply.

#### Scenario: Private docs contain a nested code checkout
- **WHEN** the outer docs repository ignores the configured code checkout directory
- **THEN** Irminsul still inventories the configured source root using the nearest code-repository ignore rules

#### Scenario: Source root has no Git repository
- **WHEN** no enclosing Git root exists
- **THEN** `.gitignore` files at and below the configured source root still apply

### Requirement: Prevent symlink escape
ID: prevent-symlink-escape
Provenance: code

Irminsul MUST NOT follow a discovered directory symlink or read a discovered file
symlink whose resolved target is outside its configured source root.

#### Scenario: File symlink remains inside the root
- **WHEN** a file symlink resolves to a regular file within the configured root
- **THEN** its lexical path is inventoried normally

#### Scenario: File symlink escapes the root
- **WHEN** a file symlink resolves outside the configured root
- **THEN** the file is omitted and the hard glob check reports an error

#### Scenario: File symlink is broken
- **WHEN** a discovered file symlink has no readable target
- **THEN** the file is omitted and the glob check reports a warning

### Requirement: Classify deleted paths consistently
ID: consistent-deleted-paths
Provenance: code

Path-only change analysis MUST use the same policy as the on-disk walker so an
ignored or explicitly excluded deletion does not become an affected source file.

#### Scenario: Excluded source file is deleted
- **WHEN** a changed path no longer exists and the configured source policy excludes it
- **THEN** change analysis does not report it as owned or undocumented source

## Detailed Design

The `[paths]` table gains three backward-compatible settings:

```toml
source_includes = []
source_excludes = []
honor_gitignore = true
```

Empty includes mean all otherwise eligible files. Non-empty includes are an
allow-list. Built-in exclusions, `.gitignore`, and explicit excludes are vetoes;
includes never resurrect them. Explicit patterns use Git wildmatch syntax and
match the same normalized POSIX display paths used by `describes:`.

Only `.gitignore` files participate. Global Git excludes and `.git/info/exclude`
are intentionally ignored so two machines produce the same inventory. Nested
ignore files use Git's last-match behavior, including negation. An ignore rule
from above a configured root that ignores the root itself is neutralized because
configuration makes that root explicit; more specific rules for descendants
continue to apply.

The walker returns structured issues as well as files and missing roots. Existing
internal callers of `walk_source_files(repo_root, source_roots)` retain a
compatibility adapter, while production consumers use the configured result.
`GlobsCheck` turns unsafe symlink issues into findings.

## Tasks

- `T1` Add source-policy configuration with backward-compatible defaults. (component: config)
- `T2` Implement ignore, pattern, and symlink handling in the shared walker. (component: checks)
- `T3` Route every inventory consumer and deleted-file classification through the policy. (component: change)
- `T4` Document and scaffold the source-policy settings. (component: init)
- `T5` Add same-repo, cross-repo, ignore, pattern, deletion, and symlink regression tests. (component: checks)

## Drawbacks

- Existing repositories may see smaller source totals and new zero-match errors
  when a `describes:` pattern only covered ignored output. That is the intended
  correction, but it is release-note-worthy.
- Nested ignore semantics add work to the filesystem walk. Ignore specifications
  are cached per directory, and ignored directories are pruned when Git semantics
  make re-inclusion impossible.
- Windows may deny symlink creation without developer mode or permission. Tests
  must skip platform creation failures while keeping pure containment tests active.

## Alternatives

- **Restrict every source root to the docs repository.** Rejected because sibling
  code repositories are a supported topology; explicit roots define the boundary.
- **Use `git ls-files`.** Rejected because source roots may be outside Git, may
  intentionally include untracked files, and must work in source archives.
- **Use `git check-ignore` per path.** Rejected because global excludes would make
  results machine-dependent and subprocess-per-file cost would be excessive.
- **Follow safe directory symlinks.** Deferred because cycle detection and duplicate
  lexical ownership require a separate, explicit policy.

## Unresolved Questions

None for the first implementation.
