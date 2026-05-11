---
id: 0002-fix-and-regen-typescript
title: "RFC-0002: irminsul fix (auto-remediation) and TypeScript reference regen"
audience: explanation
tier: 2
status: draft
---

# RFC-0002: `irminsul fix` (auto-remediation) and TypeScript reference regen

## Status

Draft. Target decision date: 2026-07-31.

## Summary

Two Sprint-2 deferrals that extend existing features rather than introducing new subsystems:

1. **`irminsul fix`** — machine-apply remediations for findings that have an unambiguous fix. The first target is `SupersessionCheck`: when an old doc's `status` is not `deprecated` or its `superseded_by` field is missing, `fix` writes the correct frontmatter rather than asking the author to do it by hand.

2. **`irminsul regen typescript`** — generate mkdocstrings-style stubs for TypeScript modules via TypeDoc.

## Motivation

### `irminsul fix`

`SupersessionCheck` emits actionable suggestions today:

```
docs/20-components/old.md  warning  [supersession]  status should be deprecated
  → set status: deprecated in docs/20-components/old.md
```

The `suggestion` field is machine-readable. The gap is purely that no command applies it. Authors re-read the finding, open the file, and make a one-line YAML edit that a computer could do faster and more reliably.

The same pattern will apply to other soft-deterministic checks over time (`mtime-drift` bumping `last_reviewed`, `parent-child` adding missing `children:` entries). The `fix` command should be designed to handle multiple check types, not just supersession.

### TypeScript reference regen

`irminsul regen python` writes mkdocstrings stubs (`:::<dotted.module>`) which autodoc renders into API reference pages. TypeScript projects have the same need but a different toolchain: TypeDoc generates JSON output from TSDoc comments; `mkdocs-material` can consume it via the `mkdocs-typedoc` plugin (or equivalently, TypeDoc's own markdown output plugin).

Teams using TypeScript as their primary language have no reference-regen story until this ships.

## Detailed Design

### `irminsul fix`

**New subcommand:**

```
irminsul fix [--profile=configured] [--dry-run] [--path=.]
```

- `--dry-run` (default false) — print what would change, write nothing.
- `--profile` mirrors `irminsul check` after RFC-0008. Only checks that expose an unambiguous `fixes` method are mutated.
- Exit 0 if nothing changed; exit 0 with a summary if changes were written; exit 1 if a fix could not be applied cleanly (e.g., frontmatter parse error in the target file).

**Fix protocol.** Each check that produces auto-fixable findings implements an optional `fixes(findings: list[Finding], graph: DocGraph) -> list[Fix]` method (not on the `Check` Protocol — just a duck-typed optional checked via `hasattr`). A `Fix` is:

```python
@dataclass(frozen=True)
class Fix:
    path: Path          # file to modify
    description: str    # human-readable, printed in dry-run
    apply: Callable[[str], str]  # takes file text, returns new text
```

The `fix` command collects all `Fix` objects, groups by path, applies in order, and writes atomically (write to `.tmp`, then rename). If two fixes conflict on the same line, the command aborts that file and reports a conflict.

**`SupersessionCheck` fixes:**

1. `status` is not `deprecated` → insert/replace `status: deprecated` in the YAML frontmatter block.
2. `superseded_by` is missing → insert `superseded_by: <new_id>` after the `supersedes:` list in the YAML frontmatter block. (The `supersedes:` field on the *new* doc tells us the old id, so the fix is deterministic.)

YAML frontmatter editing is done with `ruamel.yaml` (already a dep) to preserve comments and ordering.

**Future candidates** (not in this RFC):

- `mtime-drift` → bump `last_reviewed` to today.
- `parent-child` → append missing child ids to `children:`.
- `orphans` → add `depends_on: []` stub (partial mitigation, not a real fix).

### TypeScript reference regen

`irminsul regen typescript` invokes TypeDoc to produce a JSON manifest, then walks the manifest to emit `docs/40-reference/typescript/<package>.<Module>.md` stubs. `irminsul regen all` includes TypeScript only when TypeScript is enabled in config.

**Toolchain dependency.** TypeDoc is a Node.js tool. Rather than shell out blindly, `irminsul regen typescript` checks for `npx typedoc --version` and fails with an actionable message if Node/npx is absent:

```
TypeScript reference regen requires Node.js and TypeDoc.
Install: npm install --save-dev typedoc
Then re-run: irminsul regen typescript
```

**Output format.** Two options exist:

Option A — TypeDoc JSON → custom Markdown writer (no new mkdocs plugin required).
Option B — TypeDoc's `--plugin typedoc-plugin-markdown` (third-party) → write stubs that include the rendered output.

Recommended: **Option A**. We control the output format, keep the stub structure consistent with the Python stubs (frontmatter + a brief docstring excerpt + `::: module.path` style directive — adapted for whichever mkdocs plugin handles TS).

**Stub format:**

```markdown
---
id: <stem>
title: "<package>.<Module>"
audience: reference
tier: 1
status: draft
---

# <package>.<Module>

<!-- generated by irminsul regen typescript -->
```

The stub body is intentionally minimal in v0.3.0; authors fill in narrative prose. The generated file acts as the anchor for `describes:` coverage in the component doc and surfaces in the mkdocs nav.

**`irminsul.toml` addition:**

```toml
[regen.typescript]
enabled = true
tsconfig = "tsconfig.json"   # relative to repo root
out_dir = "docs/40-reference/typescript"
```

Detected at `init`/`init-docs-only` time when a `tsconfig.json` is present.

## Drawbacks

### `fix`

- Auto-editing frontmatter YAML carries a small risk of corrupting files with unusual YAML features (multi-line strings, anchors). Mitigated by `--dry-run`, by writing atomically, and by limiting fixes to known-safe patterns.
- The `Fix.apply: Callable` design makes testing straightforward but makes future serialisation (e.g., for a `--output-fixes=patch` flag) harder. The trade-off is acceptable for Sprint 3.

### TypeScript regen

- Node.js as a runtime dependency of a Python tool is jarring. Made explicit in the error message; not hidden.
- TypeDoc JSON schema is not formally versioned. We should pin `@typedoc/typedoc` in the project's `package.json` example and document the minimum version.

## Alternatives

### `fix`

- **`--fix` flag on `irminsul check`.** Familiar from tools like `ruff --fix`. Rejected because it conflates checking (read-only) and remediation (write). A separate command makes `--dry-run` semantics cleaner and is easier to gate in CI.
- **Interactive fix mode** (approve each change). Nice UX but complex to implement on first cut; add as `--interactive` flag in Sprint 4 if demand exists.

### TypeScript regen

- **TypeDoc markdown plugin (Option B).** Depends on a third-party npm package; we can't control its output format or update cadence. Option A costs more up-front but is more stable.
- **Defer to when VSCode extension lands** (RFC-0003). The extension could offer reference-gen as a GUI action. Rejected — CLI regen is useful independently of the extension.

## Unresolved Questions

- `fix` conflict resolution: when two `Fix.apply` functions both modify the same YAML key, which wins? First-writer? Abort with a message? Propose: abort and report; let the author run narrower fix profiles first.
- For TypeScript regen, should stub filenames use dots (`mylib.core.md`) or slashes (`mylib/core.md`) matching directory layout? Python uses dots; TypeScript packages often use directory hierarchies. Tentative: dots, consistent with Python.
- `ruamel.yaml` round-trip mode sometimes reorders keys. Should we pin key order to the canonical frontmatter field order from `DocFrontmatter`? Probably yes — document the ordering rule.
