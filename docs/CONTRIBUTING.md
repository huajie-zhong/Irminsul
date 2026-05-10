# Contributing to Irminsul docs

A few rules to keep these docs readable as the codebase grows.

1. **One fact, one home.** If you're tempted to copy-paste a definition, you've found a candidate for `GLOSSARY.md`.
2. **Code wins.** Anything that can be generated from code lives in `40-reference/` and is regenerated on CI.
3. **One audience per doc.** Tutorial, how-to, explanation, reference, ADR, runbook — pick one.
4. **Frontmatter is required** on every doc atom. CI rejects PRs that add or modify docs without it.
5. **Decisions become ADRs.** If a PR makes a choice future-you will want to know the reasoning behind, write the ADR in `50-decisions/` in the same PR.
6. **Edit the canonical doc, not its mirror.** If you find yourself editing `20-components/foo.md` to keep it in sync with `10-architecture/overview.md`, one of them is wrong.
7. **First-is-Interface.** The first file or glob listed in `describes:` is formally recognised as the component's entry point or public interface. When exploring an unfamiliar component, start here. Order subsequent globs from most-public to least-public.

CI runs `irminsul check --profile=hard` on every PR. Locally, `irminsul check` does the same.
