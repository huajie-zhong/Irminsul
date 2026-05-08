---
id: 0004-remove-children-field
title: "RFC-0004: Remove children: field — INDEX auto-owns all folder siblings"
audience: explanation
tier: 2
status: draft
owner: "@hz642"
last_reviewed: 2026-05-08
---

# RFC-0004: Remove `children:` field — INDEX auto-owns all folder siblings

## Status

Draft. Target decision date: 2026-06-30.

## Summary

The `children:` frontmatter field on `INDEX.md` files is redundant. An INDEX that exists in a folder implicitly owns every sibling `.md` file in that folder. Making this the enforced convention removes the field entirely and eliminates the verbosity of declaring what the folder structure already expresses.

## Motivation

The `children:` field was designed to give INDEX files explicit, machine-readable ownership over a declared subset of their folder siblings. The intended benefit: an INDEX could claim some files while leaving others "independent."

That scenario does not hold up. The strongest counter-argument tried was a deprecated doc that outlives its usefulness — a folder might contain an INDEX owning active components plus an old migration guide the INDEX shouldn't "claim." But a deprecated doc already self-declares its status via `status: deprecated`. There is no need for the INDEX to also signal non-ownership through omission. The `status` field is the correct place for that information.

No realistic scenario exists where a `.md` file legitimately lives in a folder alongside an INDEX but should not be owned by it. Physical co-location and ownership are the same thing in a well-structured doc tree.

## Proposed change

**`ParentChildCheck` behavior after this change:**

- If an `INDEX.md` exists in a folder, it automatically owns all sibling `.md` files. No `children:` declaration required.
- On-disk files not reachable via any inbound path (body link, `depends_on`, or folder-INDEX ownership) are orphans.
- The broad-globs ban and length cap in `ParentChildCheck` are unchanged.
- The `children:` field is removed from `DocFrontmatter`. Any existing `children:` values in docs are ignored (or flagged as unknown keys under `extra="allow"`).

**Orphan resolution:** A sibling of an INDEX is no longer an orphan by default — folder membership implies reachability. The orphan check exempts files whose folder contains an `INDEX.md`.

**When this RFC is accepted, also update `docs/00-foundation/principles.md`** to record the auto-ownership assumption as an explicit design principle: *"Physical co-location implies ownership — if a `.md` file lives in a folder that has an `INDEX.md`, it is owned by that INDEX. There is no valid scenario where a file co-locates with an INDEX but is not part of it."* That edit is intentionally deferred; adding it now would contradict the current `children:`-based behavior still in the codebase.

**Migration:** Strip `children:` from all existing `INDEX.md` files in the repo. At time of writing, the affected files are:

- `docs/20-components/INDEX.md`
- `docs/80-evolution/rfcs/INDEX.md`

The `irminsul fix` command (RFC-0002) is the natural vehicle for automating this at scale once it ships; until then, remove the field by hand as part of the implementation PR.

## Drawbacks

- **Loss of explicit completeness signalling.** Today, `children:` with a warning for unlisted on-disk siblings means the check actively tells you "a file appeared in this folder without being registered." After this change, any file dropped into a folder is silently auto-owned. The tradeoff: less noise, less ceremony, but also less explicit gate on "I intended this file to be here."
- **Harder to express intent for temporary files.** A scratch doc or work-in-progress dropped into a component folder becomes an immediate child. Mitigation: use `status: draft` and keep drafts in their own layer (`00-foundation/` or a `drafts/` folder outside the component tree).

## Alternatives

- **Keep `children:` as optional.** Folders without it use auto-ownership; folders with it use the explicit list. Rejected: optional means inconsistent. Half the codebase declares children, half doesn't; both modes need to be supported and tested.
- **Keep `children:` required.** Current behavior. Rejected per the motivation above — it encodes information the folder structure already expresses, and the only scenario where the distinction matters (`status: deprecated` docs) is already covered by the status field.

## Unresolved Questions

- Should the orphan exemption be "folder contains INDEX.md" or "file is a direct sibling of an INDEX.md"? These are the same thing stated differently, but the implementation detail matters for nested folders (grandparent case).
- After removing `children:`, the `ParentChildCheck` loses its "unlisted sibling" warning. Is there a lighter-weight replacement — e.g., a warning when a file is added to a folder without any `status:` being set? Probably out of scope for this RFC.
