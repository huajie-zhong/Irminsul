---
id: 0009-deterministic-doc-reality-audits
title: Deterministic doc reality audits
audience: explanation
tier: 2
status: stable
describes: []
---

# RFC 0009: Deterministic doc reality audits

## Summary

Add deterministic audit checks that compare stable docs against machine-readable
repo facts. These checks target dogfood failures where docs understate or
overstate the current implementation even though the correct answer is already
available from source code, config, generated references, or the doc graph.

This RFC does not solve semantic doc truth. It closes mechanical drift holes and
routes reviewer attention toward nearby prose when generated facts change.

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

This is a hard check. It should ignore fenced code blocks and RFC examples by
default. Intentional skeleton examples must carry an explicit ignore marker with
a reason:

`<!-- irminsul:ignore prose-file-reference reason="example skeleton" -->`

Long example sections can use a validated block ignore:

```text
<!-- irminsul:ignore-start prose-file-reference reason="example skeleton" -->
...
<!-- irminsul:ignore-end prose-file-reference -->
```

Unmatched block markers are findings.

### `schema-doc-drift`

Compare the generated frontmatter reference against `DocFrontmatter`. Component
docs should link to the generated reference rather than manually listing fields.

### `cli-doc-drift`

Compare the generated CLI reference against the Typer app. Stable CLI docs
should link to the generated reference rather than manually listing the complete
command surface.

### `check-surface-drift`

Compare the generated check reference against the hard, soft deterministic, and
LLM registries. This prevents stale statements such as "five hard checks ship"
when the configured hard check set has changed.

### `terminology-overload`

Warn when a configured key system term is used for multiple concepts without an
explicit disambiguation link. The default target is "coverage":

- source ownership coverage: whether source files are claimed by docs
- `CoverageCheck`: whether tier-3 docs declare valid `tests:` entries

## Implementation Plan

1. Add `prose-file-reference` as a hard deterministic check with explicit
   line-level and block ignore markers.
2. Add schema, CLI, check-surface, and terminology audits as deterministic
   warnings.
3. Generate code-derived reference docs for frontmatter fields, CLI commands,
   and check registries.
4. Keep component docs explanatory and link them to generated references for
   exact code-derived surfaces.
5. Add fixtures for the dogfood failures listed above.
6. Run configured warnings in dogfood/nightly. Use strict warning policy only
   after the repo has a clean advisory baseline.

The soft deterministic RFC 0009 checks are globally enabled by default as part
of `checks.soft_deterministic`. Projects can still override that list when they
need a narrower configured profile.

## Drawbacks

These checks require generated reference surfaces for code-derived facts. That
is extra machinery, but it is cheaper than asking reviewers or agents to infer
whether prose matches source.

## Alternatives

- Use only LLM semantic drift checks. This catches broader cases but is
  advisory, cost-bearing, and less deterministic.
- Use manually maintained structured tables in component docs. This is smaller,
  but violates the code-as-truth principle for surfaces that can be generated.
- Do nothing and rely on code review. That preserves the current dogfood gap.

## Resolved Questions

- `prose-file-reference` is hard immediately because local `.md` references are
  machine-verifiable cross-references. False positives use an explicit ignore
  marker with a reason; long examples may use a validated ignore block.
- Generated reference docs are the canonical home for code-derived schema, CLI,
  and check surfaces. A follow-up RFC defines the broader generated-reference
  system and future expansion.
