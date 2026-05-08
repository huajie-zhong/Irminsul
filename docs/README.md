# Irminsul docs

This tree follows the doc system Irminsul itself enforces. We dogfood — every PR runs `irminsul check --scope=hard` against this directory.

| Layer | What lives here |
|-------|-----------------|
| [`00-foundation/`](00-foundation/principles.md) | Why Irminsul exists; what it isn't. |
| [`10-architecture/`](10-architecture/overview.md) | System overview. |
| [`20-components/`](20-components/INDEX.md) | One doc per architectural piece. |
| `30-workflows/` | Cross-component narratives (none yet). |
| `40-reference/` | Generated. CLI surface, config schema. |
| [`50-decisions/`](50-decisions/INDEX.md) | ADRs. Append-only. |
| `60-operations/` | (Empty for a CLI tool.) |
| `70-knowledge/` | (Empty until we have user-facing tutorials.) |
| `80-evolution/` | Roadmap and risks. |
| `90-meta/` | Docs about docs, style guides, and health dashboard. |

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`GLOSSARY.md`](GLOSSARY.md).
