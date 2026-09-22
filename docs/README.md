# Irminsul docs

This tree follows the doc system Irminsul itself enforces. We dogfood — every PR runs `irminsul check` against this directory.

## Navigation Protocol

The documentation is organized into six [layers](architecture/layers.md): [foundation](foundation/INDEX.md), [architecture](architecture/INDEX.md), [components](components/INDEX.md), [decisions](decisions/INDEX.md), [rfcs](rfcs/INDEX.md), and [guides](guides/INDEX.md). Each layer sets the rules its docs follow.

## For AI Agents and Contributors

- **Code Mapping:** Every component doc in `components/` contains a `describes:` frontmatter field mapping it to source files.
- **Stability:** Refer to the `status:` field (draft | stable | deprecated | removed) to understand the reliability of a document.
- **Editing loop:** Start with `irminsul orient`, then run `irminsul context --before-edit <path...>` before changing code or docs and `irminsul context --after-edit` afterward to inspect affected knowledge and validation. The path, topic, and changed context modes remain available for focused discovery.

## Editing rules

The rules every edit follows live in [CONTRIBUTING.md](CONTRIBUTING.md); vocabulary lives in [GLOSSARY.md](GLOSSARY.md).
