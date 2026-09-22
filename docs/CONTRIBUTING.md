# Contributing to Irminsul docs

A few rules to keep these docs readable as the codebase grows.

1. **One fact, one home.** If you're tempted to copy-paste a definition, you've found a candidate for `GLOSSARY.md`.
2. **Code wins.** Anything reconstructable from code is derived on demand (e.g. `irminsul surface`), not hand-copied into prose or committed as a generated file.
3. **One reader per doc.** Write each doc for one reader in one moment: learning, doing a task, understanding, or looking something up.
4. **Frontmatter is required** on every doc atom. CI rejects PRs that add or modify docs without it.
5. **Decisions become ADRs.** If a PR makes a choice future-you will want to know the reasoning behind, write the ADR in `decisions/` in the same PR.
6. **Edit the canonical doc, not its mirror.** If you find yourself editing `components/foo.md` to keep it in sync with `architecture/overview.md`, one of them is wrong.
7. **Reality only.** Docs outside `rfcs/` describe the current main branch. A planned or deferred feature is proposed in an RFC, not documented as if it shipped.
8. **Docs land with the code.** A behaviour change and the doc changes it needs go in the same PR.
9. **Silence is a bug.** If a component cannot do something a reader would expect, say so in its `## Scope & Limitations`.
10. **First-is-Interface.** The first file or glob listed in `describes:` is formally recognised as the component's entry point or public interface. When exploring an unfamiliar component, start here. Order subsequent globs from most-public to least-public.

CI runs `irminsul check` on every PR; [enforcement](foundation/enforcement.md) describes the pipeline. Locally, `irminsul check` runs the same checks.
