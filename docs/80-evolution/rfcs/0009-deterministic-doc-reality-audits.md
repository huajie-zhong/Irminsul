---
id: 0009-deterministic-doc-reality-audits
title: Deterministic doc reality audits
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0009: Deterministic doc reality audits

## Summary

Add deterministic audit checks that compare stable docs against machine-readable
repo facts. These checks target dogfood failures where docs understate or
overstate the current implementation even though the correct answer is already
available from source code, config, or the doc graph.

## Motivation

Several current docs can pass structural checks while still confusing an agent:

1. Navigation pages name local `.md` files in prose or code spans, so broken
   references are invisible to the markdown link checker.
2. Frontmatter docs can drift from the `DocFrontmatter` schema.
3. CLI docs can drift from Typer-registered commands.
4. Check docs can drift from the hard, soft, and LLM check registries.
5. The word "coverage" can mean source ownership coverage in one doc and
   `tests:` enforcement in another.

These are not deep semantic problems. They are deterministic comparisons that
Irminsul can make mechanically.

## Detailed Design

### `prose-file-reference`

Scan stable docs for local markdown file names in prose and inline code. If the
text looks like an intended local doc reference, require either:

- a real markdown link to an existing file, or
- an explicit marker that the name is an example skeleton entry.

The check should ignore fenced code blocks and RFC examples by default.

### `schema-doc-drift`

Compare documented canonical frontmatter fields against `DocFrontmatter`.

The first implementation can require the frontmatter component doc to contain a
generated or structured field list. Later implementations can extend this to
config models and renderer options.

### `cli-doc-drift`

Compare documented top-level and grouped CLI commands against the Typer app.
Stable CLI docs should not say only `init`, `check`, and `render` ship when the
CLI also exposes `init-docs-only`, `new`, `list`, `fix`, and `regen`.

### `check-surface-drift`

Compare documented check names against the hard, soft deterministic, and LLM
registries. This prevents stale statements such as "five hard checks ship" when
the configured hard check set has changed.

### `terminology-overload`

Warn when a key system term is used for multiple concepts without an explicit
disambiguation link. The initial target is "coverage":

- source ownership coverage: whether source files are claimed by docs
- `CoverageCheck`: whether tier-3 docs declare valid `tests:` entries

## Implementation Plan

1. Add deterministic checks as soft warnings.
2. Keep each check narrowly scoped to stable docs and known high-value surfaces.
3. Add fixtures for the dogfood failures listed above.
4. Recommend running these checks in dogfood/nightly with strict warning policy.
5. Update docs to use structured or generated surfaces where possible.

## Drawbacks

These checks require docs to expose some facts in parseable form. That is extra
work, but it is cheaper than asking reviewers or agents to infer whether prose
matches source.

## Alternatives

- Use only LLM semantic drift checks. This catches broader cases but is
  advisory, cost-bearing, and less deterministic.
- Do nothing and rely on code review. That preserves the current dogfood gap.

## Unresolved Questions

- Should `prose-file-reference` become hard once false positives are understood?
- Should generated reference docs be the only allowed home for schema and CLI
  surfaces?
