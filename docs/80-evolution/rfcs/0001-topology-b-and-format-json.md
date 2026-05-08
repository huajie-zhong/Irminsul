---
id: 0001-topology-b-and-format-json
title: "RFC-0001: Topology B (sibling code repos) and structured check output"
audience: explanation
tier: 2
status: draft
owner: "@hz642"
last_reviewed: 2026-05-08
---

# RFC-0001: Topology B (sibling code repos) and structured check output

## Status

Draft. Target decision date: 2026-06-30.

## Summary

Two quality-of-life gaps in v0.2.0:

1. **Topology B** — `irminsul check` cannot cross a repo boundary. When a docs repo lives alongside (not inside) a code repo (`../my-code/`), `walk_source_files` and `_to_repo_relative` raise `ValueError` because they call `path.relative_to(repo_root)` on a path that is outside the docs root. Supporting sibling repos requires rethinking how source paths are represented internally.

2. **`--format=json`** — `irminsul check` prints human-readable text only. There is no machine-consumable output, which limits integration into CI dashboards, editor tooling, and scripted triage workflows.

Both are low-risk, self-contained changes that unlock the same category of user: teams that want to integrate Irminsul into a broader CI pipeline or a polyrepo workspace.

## Motivation

### Topology B

v0.2.0 documents the constraint explicitly in `docs/10-architecture/tooling.md`:

> "Code is in a separate git repo" is supported; "code lives at a sibling/unrelated filesystem path" is not yet — that's Topology B.

The path constraint is in two places:

- `src/irminsul/checks/globs.py` — `walk_source_files` returns `Path` objects that callers assume are relative to `repo_root`.
- `src/irminsul/docgraph.py` — `_to_repo_relative` calls `path.relative_to(repo_root)`, raising if the path is outside.

Topology A (code as a gitignored subfolder) is an awkward workaround for this. Teams that already have a public code repo and want to add a private docs repo should not need to clone the code into the docs repo — they should be able to point `source_roots` at `../my-code/src` and have checks work.

### `--format=json`

The `Finding` dataclass already carries all the structured data (`check`, `severity`, `message`, `path`, `doc_id`, `line`, `suggestion`). Serialising it to JSON is a small amount of code that unlocks:

- Editor extensions reading findings directly (RFC-0003).
- CI pipeline steps that filter or annotate findings without screen-scraping.
- `irminsul list` commands already support `--format=json`; `check` should too.

## Detailed Design

### Topology B

**Path representation change.** Replace "source paths are always relative to `repo_root`" with "source paths are relative to their own `source_root`." Internally, track `(source_root: Path, rel: PurePosixPath)` pairs — or equivalently, keep absolute paths through the pipeline and only make them relative at display time.

Concrete changes:

- `walk_source_files(repo_root, source_roots)` → returns `list[tuple[Path, PurePosixPath]]` where the first element is the absolute path and the second is the display-relative path (relative to `source_root`). This is additive; callers that only need the display path keep working.
- `_to_repo_relative` in `docgraph.py` is replaced by a display helper that falls back to `path.relative_to(source_root)` when `path` is outside `repo_root`.
- `GlobsCheck`, `UniquenessCheck`, `SemanticDriftCheck`, `MtimeDriftCheck` all use `walk_source_files`; each needs to unpack the new tuple. The internal logic is unchanged.
- `irminsul.toml` `source_roots` accepts any path string (absolute, repo-relative, or `..`-relative). Resolved at load time via `(repo_root / entry).resolve()`.

`init-docs-only` already validates that Topology A only works for nested subfolders. After this change, `init-docs-only --layout=sibling --code-repo ./path/to/code` becomes valid and writes `source_roots = ["../path/to/code/src"]` (or detected sub-roots) rather than a nested subfolder.

**No change to `irminsul init`** (single-repo) — `repo_root` is the single workspace root; all source paths are inside it.

### `--format=json`

Add `--format=plain|json` (default `plain`) to `irminsul check`. When `json`:

```json
{
  "findings": [
    {
      "check": "frontmatter",
      "severity": "error",
      "message": "...",
      "path": "docs/20-components/foo.md",
      "doc_id": "foo",
      "line": null,
      "suggestion": null
    }
  ],
  "summary": { "errors": 1, "warnings": 0, "info": 0 }
}
```

`path` is POSIX-normalised and repo-relative (empty string if `None`). Exit codes are unchanged.

## Drawbacks

- **Topology B path change** touches every check that calls `walk_source_files`. The change is mechanical but has a wide blast radius; every test fixture that builds a source path needs review.
- **`--format=json`** is additive and risk-free, but once shipped it becomes a public API contract. The schema must stay stable or be versioned.

## Alternatives

### Topology B

- **Keep Topology A only.** Simpler, but forces awkward repo layouts on teams that cannot nest a public code repo inside a private docs repo (e.g., GitHub visibility constraints).
- **`--source-root` CLI flag instead of config change.** More discoverable for one-off runs but doesn't help with CI workflows that need a committed config.

### `--format=json`

- **GitHub Annotations output** (`--format=github`). Could emit `::error file=...,line=...,col=...::message` directly. Useful for PR annotations. Can be a follow-on; JSON is the more general primitive.
- **SARIF output.** Standard for static-analysis tools; heavy schema. Probably Sprint 4+.

## Unresolved Questions

- Should `source_roots` with `..`-relative paths be forbidden in single-repo `init` to avoid confusion? Or rely on the user knowing what they're doing?
- Does `git/mtime.py` work cross-repo (the source files may be in a different `.git` tree)? `gitpython` can open any repo root — `last_commit_time` already takes `repo_root` as a parameter, but Topology B source files live in a different git repo. Need to resolve which repo root to pass for mtime checks.
- JSON schema version strategy: embed `"version": 1` in the output from day one so consumers can detect breaking changes.
